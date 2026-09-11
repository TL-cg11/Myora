"""정책 버전 스위치.

버전마다 실제 규칙 문구를 통째로 얼려 둔 파일(v1_1.py, ...)을 두고, 지금 서비스가
쓰는 버전은 이 파일의 ACTIVE 한 줄로만 정한다. "1.1로 롤백"은 ACTIVE를
policy_versions.v1_1로 되돌리는 것으로 끝난다 — 그 시점 문구를 다시 알아내거나
git 이력을 뒤질 필요가 없다.

새 버전을 만들 때: 이 디렉터리에 v1_2.py 같은 새 파일을 만들어 이전 버전의
VERSION, COMMON_POLICY, INPUT_CHECK_INSTRUCTION, OUTPUT_CHECK_INSTRUCTION,
RESTRICT, INCIVILITY, OUT_OF_SCOPE, OUT_OF_SCOPE_GUIDE, CRISIS를 전부 채운 뒤
아래 ACTIVE만 그 모듈로 바꾼다. 이미 배포된 버전 파일은 고치지 않는다 — 고치면
그 버전 라벨이 가리키는 내용이 조용히 달라져서 롤백이 의미를 잃는다.
"""

from app.prompts.policy_versions import v1_1 as ACTIVE

__all__ = ["ACTIVE"]
