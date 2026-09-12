"""활성 정책 버전에서 라벨과 공통 규칙만 꺼내 온다.

실제 규칙 문구는 여기에 없다. app/prompts/policy_versions/를 보라. 여기서
COMMON_POLICY를 직접 고치면 버전 번호와 내용이 다시 어긋난다.
"""

from app.prompts.policy_versions import ACTIVE

POLICY_VERSION = ACTIVE.VERSION
COMMON_POLICY = ACTIVE.COMMON_POLICY
