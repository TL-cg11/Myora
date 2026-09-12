# 탐지 위치를 이용해 문자열을 치환한다. 원본 문자열은 직접 변경하지 않는다.
from .models import Detection


# 잘못된 범위는 실패시키고 겹친 범위의 합집합을 가려 민감 문자의 잔여 노출을 막는다.
def mask(text: str, detections: list[Detection]) -> str:
    """Merge overlapping spans so lower-priority matches cannot expose a suffix."""
    ordered = sorted(detections, key=lambda d: (d.start, d.end))
    groups = []
    for d in ordered:
        if not (0 <= d.start < d.end <= len(text)):
            raise ValueError("INVALID_SPAN")
        if groups and d.start < groups[-1][1]:
            start, end, replacement = groups[-1]
            groups[-1] = (start, max(end, d.end), "[REDACTED]")
        else:
            groups.append((d.start, d.end, d.replacement))
    result = text
    # 뒤쪽부터 치환해야 앞쪽에 남아 있는 원본 offset이 밀리지 않는다.
    for start, end, replacement in reversed(groups):
        result = result[:start] + replacement + result[end:]
    return result
