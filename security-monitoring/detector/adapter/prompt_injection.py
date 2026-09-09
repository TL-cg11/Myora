# Prompt Injection 탐지: 정책의 prompt_injection_detection이 켜진 자유 텍스트에만 적용한다.
"""Regex screen for prompt-injection attempts in user questions.

마스킹 대상이 아니라 탐지 전용이다. 본문은 그대로 두고 보안 이벤트만 추가한다.
"""

from __future__ import annotations

import re

from app.models import Detection

RULE_ID = "PROMPT_INJECTION"
RULE_VERSION = "1.0"
CATEGORY = "BEHAVIOR"
RISK_SCORE = 70
RISK_LEVEL = "MEDIUM"
CONFIDENCE = 0.6
# 지시 무시, 역할 변경, 시스템 프롬프트 노출 요구, 대화 구분자 위조를 본다.
PATTERNS = (
    re.compile(
        r"(?:ignore|disregard|forget|override)\s+(?:all\s+|any\s+|the\s+)?"
        r"(?:previous|prior|above|earlier|system)\s+"
        r"(?:instruction|instructions|prompt|prompts|rule|rules|message|messages)",
        re.IGNORECASE,
    ),
    re.compile(r"(?:이전|앞|위)의?\s*(?:모든\s*)?(?:지시|명령|규칙|프롬프트)[^\n]{0,10}?무시"),
    re.compile(r"(?:system|developer)\s*prompt\s*(?:을|를|is|:)?\s*(?:reveal|show|print|출력|알려|보여)", re.IGNORECASE),
    re.compile(r"(?:시스템|개발자)\s*프롬프트[^\n]{0,12}?(?:알려|보여|출력|공개)"),
    re.compile(r"(?:you\s+are\s+now|from\s+now\s+on\s+you\s+are|act\s+as)\s+(?:a|an|the)?\s*\w", re.IGNORECASE),
    re.compile(r"이제부터\s*(?:너|당신|넌)[^\n]{0,12}?(?:이다|야|해라|행동)"),
    re.compile(r"\b(?:jailbreak|DAN\s+mode|developer\s+mode|do\s+anything\s+now)\b", re.IGNORECASE),
    re.compile(r"탈옥\s*(?:모드|해줘|해라)"),
    re.compile(r"<\|(?:im_start|im_end|system|endoftext)\|>", re.IGNORECASE),
    re.compile(r"^\s*(?:###|---)\s*(?:system|instruction|assistant)\b", re.IGNORECASE | re.MULTILINE),
)


# 겹치는 구간은 하나로 합쳐 같은 문장을 여러 번 세지 않는다.
def _merge(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    merged: list[tuple[int, int]] = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


# 탐지 위치만 남긴다. replacement는 마스킹에 사용하지 않는다.
def detect(text: str, field: str = "/body") -> list[Detection]:
    if not text:
        return []
    spans = [
        (match.start(), match.end())
        for pattern in PATTERNS
        for match in pattern.finditer(text)
    ]
    return [
        Detection(RULE_ID, CATEGORY, RISK_LEVEL, RISK_SCORE, CONFIDENCE,
                  start, end, "[REDACTED]", field, RULE_VERSION)
        for start, end in _merge(spans)
    ]
