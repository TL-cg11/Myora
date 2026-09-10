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
        question = '제 연락처는 010-1234-5678이고 관상이 궁금해요'
        result, call = await self.run_with(
            ['{"decision":"allow","rules":[],"crisis_kind":"none"}', '얼굴 비율 설명입니다.', '{"decision":"allow","rules":[]}'],
            question=question,
        )
        self.assertTrue(result.generated)
        self.assertEqual(call.await_count, 3)
        inspected = call.await_args_list[0].args[0][1]['content']
        messages = call.await_args_list[1].args[0]
        self.assertIn('010-1234-5678', inspected)
        self.assertIn(question, messages[1]['content'])
        self.assertEqual(result.question, question)
        self.assertNotIn('aspect_ratio', messages[0]['content'])
        self.assertEqual(messages[1]['role'], 'user')

    async def test_inspectors_explicitly_allow_safe_fortune_conversation(self):
        _, call = await self.run_with([
            '{"decision":"allow","rules":[],"crisis_kind":"none"}',
            '관계의 흐름을 천천히 돌아보세요.',
            '{"decision":"allow","rules":[]}',
        ], question='그럼 연애 쪽은 어때?')
        input_instruction = call.await_args_list[0].args[0][0]['content']
        output_instruction = call.await_args_list[2].args[0][0]['content']
        self.assertIn('가벼운\n자기성찰 조언은 허용', input_instruction)
        self.assertIn('미래형 표현', output_instruction)
        self.assertIn('단어만으로 차단하지 말고', output_instruction)

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

    async def test_out_of_scope_is_answered_in_persona_after_output_check(self):
        result, call = await self.run_with([
            '{"decision":"out_of_scope","rules":["G01"],"crisis_kind":"none"}',
            '저는 타로 보는 고양이 묘라예요. 카드에 대해 물어봐 주세요.',
            '{"decision":"allow","rules":[]}',
        ], question='오늘 역삼동 날씨 어때?')
        self.assertIn('묘라', result.answer)
        self.assertTrue(result.generated)
        self.assertEqual(call.await_count, 3)
        # 생성 모델에게 범위 밖이라는 사실과 답하지 말라는 지시가 함께 전달된다.
        self.assertIn('상담 범위 밖', call.await_args_list[1].args[0][0]['content'])
        # 유해하지 않으므로 질문 원문을 지우지 않는다.
        self.assertEqual(result.question, '오늘 역삼동 날씨 어때?')

    async def test_out_of_scope_answer_still_passes_output_check(self):
        result, _ = await self.run_with([
            '{"decision":"out_of_scope","rules":["G01"],"crisis_kind":"none"}',
            '역삼동은 오늘 맑아요.',
            '{"decision":"block","rules":["G01"]}',
        ], question='오늘 역삼동 날씨 어때?')
        self.assertNotIn('맑아요', result.answer)

    async def test_out_of_scope_failure_falls_back_to_reviewed_notice(self):
        result, _ = await self.run_with([
            '{"decision":"out_of_scope","rules":["G01"],"crisis_kind":"none"}',
            TimeoutError(),
        ], question='오늘 역삼동 날씨 어때?')
        self.assertEqual(result.answer, g.OUT_OF_SCOPE)

    async def test_restrict_still_skips_generation(self):
        result, call = await self.run_with(
            ['{"decision":"restrict","rules":["G03"],"crisis_kind":"none"}'],
            question='내가 언제 죽어?')
        self.assertEqual(result.answer, g.RESTRICT)
        self.assertEqual(call.await_count, 1)
        self.assertNotIn('죽어', result.question)

    async def test_checker_is_told_that_self_introduction_is_in_scope(self):
        """완화 지시문이 사라지면 '니 이름 뭐야?'가 다시 범위 밖으로 막힌다."""
        _, call = await self.run_with(['{"decision":"allow","rules":[],"crisis_kind":"none"}',
                                       '묘라예요', '{"decision":"allow","rules":[]}'],
                                      question='니 이름 뭐야?')
        instruction = call.await_args_list[0].args[0][0]['content']
        self.assertIn('이름, 정체, 할 수 있는 일, 이용 방법', instruction)
        self.assertIn('역할극 우회가 아닙니다', instruction)
        self.assertIn('페르소나로 자연스럽게 답하세요', instruction)

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

    def test_existing_redaction_does_not_hide_birth_datetime(self):
        private_values = (
            'person@example.com', '900101-1234567', '010-1234-5678',
            'https://example.com/private', 'sk-test_secret',
        )
        for value in private_values:
            self.assertNotIn(value, g.redact(f'값은 {value} 입니다'))
        birth_context = '생년월일 1995-05-15, 출생 시각 12:30, 일주 甲子'
        self.assertEqual(g.redact(birth_context), birth_context)

    def test_direct_identifier_detection_matches_redact_scope(self):
        for value in ('person@example.com', '900101-1234567', '010-1234-5678',
                      'https://example.com/private', 'sk-test_secret'):
            self.assertTrue(g.contains_direct_identifier(f'질문에 {value} 포함'), value)
        for value in ('지금 이 일을 계속 해도 될까요?', '대운은 1 11 21 31 41 51 61 71 순서인가요?',
                      '1995년생인데 올해 흐름이 궁금해요'):
            self.assertFalse(g.contains_direct_identifier(value), value)

    async def test_check_calls_use_the_shorter_check_timeout(self):
        import httpx
        seen = []
        original = httpx.AsyncClient

        def client(**kw):
            seen.append(kw['timeout'].read)
            return original(transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json={'choices': [
                    {'finish_reason': 'stop', 'message': {'content': '{}'}}]})), **kw)

        with patch.object(ai_client.httpx, 'AsyncClient', client):
            await ai_client.completion([], 'fake', 'model', check=True)
            await ai_client.completion([], 'fake', 'model')
        self.assertEqual(seen, [ai_client.settings.ai_check_timeout,
                                ai_client.settings.ai_request_timeout])

    async def test_transport_rejects_truncated_response_and_uses_common_settings(self):
        import httpx
        captured = []
        def handler(request):
            import json
            captured.append(json.loads(request.content))
            return httpx.Response(200, json={'choices':[{'finish_reason':'length','message':{'content':'partial'}}]})
        original = httpx.AsyncClient
        with patch.object(ai_client.httpx, 'AsyncClient', lambda **kw: original(transport=httpx.MockTransport(handler), **kw)):
            with ai_client.capture_ai_calls() as calls:
                with self.assertRaises(ValueError):
                    await ai_client.completion([], 'fake', 'model')
        self.assertFalse(captured[0]['stream'])
        self.assertEqual(captured[0]['max_tokens'], ai_client.settings.ai_max_tokens)
        self.assertEqual(calls[0]['phase'], 'generation')
        self.assertFalse(calls[0]['success'])


class TimeoutBudgetTests(unittest.TestCase):
    """개별 호출이 정상인데 전체 예산이 모자라 장애 응답만 나오는 상황을 막는다."""

    def test_default_budget_covers_two_checks_and_one_generation(self):
        s = ai_client.settings
        self.assertGreaterEqual(
            s.ai_total_timeout, s.ai_check_timeout * 2 + s.ai_request_timeout
        )

    def test_startup_rejects_a_budget_that_cannot_finish(self):
        from app.config import Settings
        with self.assertRaises(ValueError) as raised:
            Settings(ai_check_timeout=10, ai_request_timeout=20, ai_total_timeout=25)
        self.assertIn('AI_TOTAL_TIMEOUT', str(raised.exception))
