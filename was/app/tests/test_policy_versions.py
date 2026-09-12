"""정책 버전 스위치가 실제로 스냅샷을 통째로 바꿔치기하는지 확인한다.

app/prompts/guardrail.py, app/services/guardrail_responses.py는 모듈이 처음
로드될 때 ACTIVE의 값을 자기 이름으로 복사해 둔다. 그래서 서버를 재시작해야
새 버전이 반영된다 — 실행 중인 프로세스의 값을 실시간으로 바꾸지 않는다.
이 사실을 놓치면 "버전을 바꿨는데 왜 그대로냐"는 혼동이 생긴다.
"""

import importlib
import unittest
from unittest.mock import patch

from app.prompts import policy_versions
from app.prompts.policy_versions import v1_1


class FakeV12:
    """실제 v1_2.py 대신 쓰는 최소 흉내. 필드 이름만 v1_1과 맞춘다."""

    VERSION = "1.2"
    COMMON_POLICY = "테스트용 새 정책 문구"
    INPUT_CHECK_INSTRUCTION = "테스트 입력 지시"
    OUTPUT_CHECK_INSTRUCTION = "테스트 출력 지시"
    RESTRICT = "테스트용 새 제한 문구"
    INCIVILITY = "테스트 욕설 안내"
    OUT_OF_SCOPE = "테스트 범위 밖"
    OUT_OF_SCOPE_GUIDE = "테스트 가이드"
    CRISIS = {"self_harm": "x", "abuse": "x", "violence": "x"}


class PolicyVersionSwitchTests(unittest.TestCase):
    def test_v1_1_snapshot_has_every_field_the_switch_needs(self):
        """새 버전 파일을 만들 때 빠뜨리기 쉬운 필드를 여기서 미리 걸러낸다."""
        required = (
            "VERSION", "COMMON_POLICY", "INPUT_CHECK_INSTRUCTION",
            "OUTPUT_CHECK_INSTRUCTION", "RESTRICT", "INCIVILITY",
            "OUT_OF_SCOPE", "OUT_OF_SCOPE_GUIDE", "CRISIS",
        )
        for field in required:
            self.assertTrue(hasattr(v1_1, field), field)

    def test_switching_active_requires_a_restart_not_a_live_reload(self):
        """실행 중인 프로세스는 ACTIVE를 바꿔도 즉시 반영하지 않는다.

        guardrail.py/guardrail_responses.py가 로드 시점 값을 자기 이름으로
        복사해 두기 때문이다. 재시작(여기서는 importlib.reload로 흉내)해야
        새 버전이 실제로 적용된다.
        """
        import app.prompts.guardrail as g
        import app.services.guardrail_responses as r

        original_version = g.POLICY_VERSION
        original_restrict = r.RESTRICT
        try:
            with patch.object(policy_versions, "ACTIVE", FakeV12):
                # 재시작 전: 이미 로드된 모듈은 그대로다.
                self.assertEqual(g.POLICY_VERSION, original_version)
                self.assertEqual(r.RESTRICT, original_restrict)

                # 재시작 흉내: 모듈을 다시 불러오면 새 버전이 반영된다.
                importlib.reload(g)
                importlib.reload(r)
                self.assertEqual(g.POLICY_VERSION, "1.2")
                self.assertEqual(r.RESTRICT, "테스트용 새 제한 문구")
        finally:
            # 다른 테스트에 영향이 남지 않도록 실제 1.1로 되돌려 다시 불러온다.
            importlib.reload(g)
            importlib.reload(r)
            self.assertEqual(g.POLICY_VERSION, "1.1")
            self.assertEqual(r.RESTRICT, original_restrict)


if __name__ == "__main__":
    unittest.main()
