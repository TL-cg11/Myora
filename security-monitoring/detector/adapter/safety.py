# 발행 직전 안전장치: 마스킹이 빠진 결과를 결과 topic에 올리지 않는다.
"""Outbound guard mirroring the consumer-side masking safety check.

luck-nginx의 ``security_sink.common.validate_masking_safety``와 같은 패턴을 사용한다.
C의 sink가 거절할 메시지를 먼저 걸러 dead-letter로 보내기 위한 사본이며,
원본이 바뀌면 이 파일도 함께 갱신한다.
"""

from __future__ import annotations

import json
import re
from typing import Any

SENSITIVE_PATTERNS = (
    re.compile(r"\b\d{6}-[1-4]\d{6}\b"),
    re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
    re.compile(r"\b01[016789]-?\d{3,4}-?\d{4}\b"),
    re.compile(r"\b(?:\d[ -]?){12,18}\d\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b", re.IGNORECASE),
    re.compile(r"\b(?:AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{20,}|gh[pousr]_[0-9A-Za-z]{20,})\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{8,}\b", re.IGNORECASE),
    re.compile(
        r"\b(?:authorization|api[_-]?key|secret[_-]?key)\s*[:=]\s*(?!\[[A-Z_]+\])\S+",
        re.IGNORECASE,
    ),
    re.compile(
        r"https?://(?:localhost|127\.0\.0\.1|10(?:\.\d{1,3}){3}|"
        r"192\.168(?:\.\d{1,3}){2}|172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2})"
        r"(?::\d+)?(?:[/\w.?=&%-]*)?",
        re.IGNORECASE,
    ),
    re.compile(
        r"https?://(?:100\.(?:6[4-9]|[7-9]\d|1[01]\d|12[0-7])(?:\.\d{1,3}){2}|"
        r"169\.254(?:\.\d{1,3}){2}|\[?::1\]?|"
        r"[a-z0-9-]+\.(?:internal|local|lan)|[a-z0-9-]+(?=[:/]))"
        r"(?::\d+)?(?:[/\w.?=&%-]*)?",
        re.IGNORECASE,
    ),
)


# 마스킹이 남지 않은 값이 있는지 확인한다. 원문은 예외 메시지에 넣지 않는다.
def contains_sensitive(*values: Any) -> bool:
    rendered = "\n".join(
        value
        if isinstance(value, str)
        else json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        for value in values
        if value is not None
    )
    return any(pattern.search(rendered) for pattern in SENSITIVE_PATTERNS)
