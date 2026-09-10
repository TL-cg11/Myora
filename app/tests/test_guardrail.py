import unittest
from dataclasses import replace
from unittest.mock import AsyncMock, patch
from pydantic import ValidationError
from app.services import ai_client
from app.services import guardrail as g

class GuardrailTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.config = patch.object(g, 'settings', replace(g.settings, deepseek_face_api_key='fake'))
        self.config.start()
        self.addCleanup(self.config.stop)

    async def run_with(self, responses, question='얼굴형 설명', context='{"aspect_ratio":1.3}'):
        with patch.object(g, 'completion', AsyncMock(side_effect=responses)) as call:
            result = await g.safe_answer('face', '페르소나', context, question)
            return result, call

    async def test_approved_answer_requires_three_calls(self):
        result, call = await self.run_with(['{"decision":"allow","rules":[],"crisis_kind":"none"}', '얼굴 비율 설명입니다.', '{"decision":"allow","rules":[]}'])
        self.assertTrue(result.generated)
        self.assertEqual(call.await_count, 3)
        messages = call.await_args_list[1].args[0]
        self.assertNotIn('aspect_ratio', messages[0]['content'])
        self.assertEqual(messages[1]['role'], 'user')

    async def test_blocked_output_is_never_returned(self):
        unsafe = '당신은 일찍 죽을 가능성이 있어요. 재미로 보세요.'
        result, _ = await self.run_with(['{"decision":"allow","rules":[],"crisis_kind":"none"}', unsafe, '{"decision":"block","rules":["G03"]}'])
        self.assertNotIn(unsafe, result.answer)
        self.assertFalse(result.generated)

    async def test_input_crisis_skips_generation_and_raw_storage(self):
        result, call = await self.run_with(['{"decision":"crisis","rules":["G07"],"crisis_kind":"abuse"}'], question='부모에게 맞는 것도 팔자야?')
        self.assertEqual(result.answer, g.CRISIS['abuse'])
        self.assertEqual(call.await_count, 1)
        self.assertNotIn('부모', result.question)

    async def test_input_failure_skips_generation(self):
        for response in ['{}', 'not json', '{"decision":"allow","rules":["G03"],"crisis_kind":"none"}', TimeoutError()]:
            result, call = await self.run_with([response])
            self.assertEqual(result.answer, g.FALLBACK)
            self.assertEqual(call.await_count, 1)

    async def test_output_failure_hides_generation(self):
        result, _ = await self.run_with(['{"decision":"allow","rules":[],"crisis_kind":"none"}', '원본', '{"decision":"allow","rules":[],"extra":true}'])
        self.assertEqual(result.answer, g.FALLBACK)

    async def test_private_output_stops_before_semantic_call(self):
        result, call = await self.run_with(['{"decision":"allow","rules":[],"crisis_kind":"none"}', '전화번호 010-1234-5678'])
        self.assertEqual(result.answer, g.RESTRICT)
        self.assertEqual(call.await_count, 2)

    async def test_missing_key_never_calls_provider(self):
        with patch.object(g, 'settings', replace(g.settings, deepseek_face_api_key='')):
            result, call = await self.run_with([])
        self.assertEqual(result.answer, g.FALLBACK)
        call.assert_not_awaited()

    def test_schema_rejects_unknown_rule_and_contradictions(self):
        for raw in ['{"decision":"block","rules":[]}', '{"decision":"allow","rules":["G99"]}']:
            with self.assertRaises(ValidationError):
                g.OutputDecision.model_validate_json(raw)

    def test_risk_level_is_computed_by_server(self):
        self.assertEqual(g.risk_level('allow', []), 'LOW')
        self.assertEqual(g.risk_level('out_of_scope', ['G01']), 'MEDIUM')
        self.assertEqual(g.risk_level('block', ['G03']), 'HIGH')
        self.assertEqual(g.risk_level('crisis', ['G07']), 'CRITICAL')

    async def test_transport_rejects_truncated_response_and_uses_common_settings(self):
        import httpx
        captured = []
        def handler(request):
            import json
            captured.append(json.loads(request.content))
            return httpx.Response(200, json={'choices':[{'finish_reason':'length','message':{'content':'partial'}}]})
        original = httpx.AsyncClient
        with patch.object(ai_client.httpx, 'AsyncClient', lambda **kw: original(transport=httpx.MockTransport(handler), **kw)):
            with self.assertRaises(ValueError):
                await ai_client.completion([], 'fake', 'model')
        self.assertFalse(captured[0]['stream'])
        self.assertEqual(captured[0]['max_tokens'], ai_client.settings.ai_max_tokens)
