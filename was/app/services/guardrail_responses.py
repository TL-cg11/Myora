"""고정 안내 문구.

FALLBACK은 정책과 무관한 장애 메시지라 여기 그대로 둔다. 나머지는 정책 결정이
담긴 문구라 활성 정책 버전(app/prompts/policy_versions)에서 가져온다 — 버전을
롤백하면 이 문구들도 그 시점 그대로 같이 되돌아간다.
"""

from app.prompts.policy_versions import ACTIVE

FALLBACK = "지금은 답변을 안전하게 확인하지 못했어요. 잠시 후 다시 시도해 주세요."

RESTRICT = ACTIVE.RESTRICT
INCIVILITY = ACTIVE.INCIVILITY
OUT_OF_SCOPE = ACTIVE.OUT_OF_SCOPE
OUT_OF_SCOPE_GUIDE = ACTIVE.OUT_OF_SCOPE_GUIDE
CRISIS = ACTIVE.CRISIS
