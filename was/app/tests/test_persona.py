import unittest

from app.prompts import COMMON_STYLE, PERSONA
from app.prompts.guardrail import COMMON_POLICY


class PersonaConsistencyTests(unittest.TestCase):
    """세 서비스가 같은 형식 규칙을 받고, 안전 규칙은 한 곳에만 두게 한다."""

    def test_every_service_shares_the_same_style_block(self):
        self.assertEqual(set(PERSONA), {'saju', 'tarot', 'face'})
        for service, persona in PERSONA.items():
            self.assertIn(COMMON_STYLE.strip(), persona, service)

    def test_answer_shape_rules_do_not_diverge(self):
        # 타로만 '3~4문장'이어서 답변 길이가 서비스마다 달랐다.
        for service, persona in PERSONA.items():
            self.assertIn('2~4개의 짧은 문단', persona, service)
            self.assertIn('이모지는 답변 전체에서 1개 이하', persona, service)
            self.assertNotIn('문장 안에', persona, service)

    def test_personas_do_not_restate_common_policy(self):
        """중복 지시는 정책을 바꿀 때 서비스마다 다르게 남는 원인이 된다."""
        duplicated = ('API 키', '시스템 프롬프트', '내부 프롬프트', '전문가와 상의',
                      '오락·참고용', '단정하지')
        for service, persona in PERSONA.items():
            for phrase in duplicated:
                self.assertNotIn(phrase, persona, f'{service}: {phrase}')

    def test_each_service_keeps_its_own_evidence_and_identity(self):
        for service, evidence in (('saju', '사주 결과'), ('tarot', '타로 결과'),
                                  ('face', '관상 결과')):
            self.assertIn(evidence, PERSONA[service])
            self.assertIn('묘라', PERSONA[service])
        self.assertIn('정/역방향', PERSONA['tarot'])
        self.assertIn('사진을 직접 보았다고', PERSONA['face'])
        self.assertIn('한자와 한글 뜻', PERSONA['saju'])

    def test_safety_rules_still_reach_the_model_through_common_policy(self):
        """페르소나에서 뺀 규칙이 공통 정책에 실제로 남아 있어야 한다.

        중복 제거가 안전 규칙 삭제가 되면 세 서비스가 동시에 규칙을 잃는다.
        """
        for phrase in ('존댓말', '오락', '의료', '확정', '관상', '개인정보', '내부 지침'):
            self.assertIn(phrase, COMMON_POLICY, phrase)


if __name__ == '__main__':
    unittest.main()
