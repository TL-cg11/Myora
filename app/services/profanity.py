"""욕설 감지와 마스킹.

의미 검사만으로는 '어느 글자가 욕설인지'를 알 수 없어 가려서 보여 줄 수 없다.
그래서 위치를 아는 로컬 규칙을 쓴다. 우회(ㅅㅂ, 시1발 등)를 전부 막지는 못하므로
완전한 차단 수단으로 취급하지 않는다. 미탐은 출력 검사와 평가 집합으로 관리한다.

정상 단어에 부분 문자열로 들어가는 오탐을 피하려고 패턴을 좁게 잡는다.
"""

import re
import unicodedata

# 자모 반복·숫자 치환 같은 흔한 변형까지만 본다. 넓히면 정상 단어를 먹는다.
_PROFANITY = (
    # '시발점', '시발역'처럼 정상 단어에 들어가는 경우는 제외한다.
    r"[시씨]+[1발벌바빠]+[랄로]?(?![점역차])",
    r"ㅅ+ㅂ+",
    r"[좆좃존]같",
    r"[개게]새+[끼키기]",
    r"병+신+",
    r"지+랄+",
    r"[엿옘]같",
    r"[씹씨]+[발빨]",
    r"미친[놈년]",
    r"존나+",
    r"[띠씨]발",
    r"[꺼거]져",
    r"닥쳐",
    r"fuck\w*",
    r"shit\w*",
    r"bitch\w*",
)

_PATTERN = re.compile("|".join(_PROFANITY), re.IGNORECASE)

# 눈으로는 구분되지 않는 회피를 펴 준다. '씨\u200b발'은 화면에 '씨발'로 보이지만
# 사이에 제로폭 문자가 있어 그대로는 매칭되지 않는다. 전각·원문자도 마찬가지다.
# 정상 한국어 문장은 이 변환에 영향을 받지 않는다.
_INVISIBLE = re.compile(r"[\u200b-\u200f\u2060\ufeff]")


def normalize(text: str) -> str:
    return _INVISIBLE.sub("", unicodedata.normalize("NFKC", text))


def mask_profanity(text: str) -> tuple[str, bool]:
    """욕설을 가린 문장과 감지 여부를 함께 돌려준다.

    정규화한 문장을 기준으로 치환한다. 원문에서 치환하면 제거된 제로폭 문자만큼
    위치가 어긋나 엉뚱한 글자를 가린다. 정규화가 바꾸는 것은 보이지 않는 문자와
    전각·호환 문자뿐이라 사용자가 읽는 모습은 달라지지 않는다.
    """
    text = normalize(text)
    found = False

    def replace(match: re.Match) -> str:
        nonlocal found
        found = True
        return "■" * max(2, len(match.group()))

    return _PATTERN.sub(replace, text), found


def contains_profanity(text: str) -> bool:
    return bool(_PATTERN.search(normalize(text)))
