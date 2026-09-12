# 자격증명 패턴 검사: 키의 실제 유효성을 외부 서비스에 조회하지 않는다.
import re

from ..models import Detection


# 텍스트에서 민감 패턴의 위치와 치환 정책을 수집한다.
def detect(text: str) -> list[Detection]:
    results = []

    # 비밀정보 탐지를 등록하되 이미 가린 토큰은 건너뛴다.
    def add(rule, start, end, score):
        if text[start:end].startswith("[REDACTED"):
            return
        results.append(Detection(rule, "SECRET", "CRITICAL" if score >= 95 else "HIGH",
                                 score, 0.95, start, end, "[REDACTED]"))

    for m in re.finditer(r"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----[\s\S]*?(?:-----END (?:[A-Z ]+ )?PRIVATE KEY-----|\Z)", text):
        add("PRIVATE_KEY", m.start(), m.end(), 100)
    for m in re.finditer(r"\b(?:mysql(?:\+pymysql)?|mariadb|postgres(?:ql)?|mongodb(?:\+srv)?)://[^\s\"'<>]+", text, re.I):
        add("DB_CONNECTION_STRING", m.start(), m.end(), 95)
    for m in re.finditer(r"\b(?:Bearer|Basic)\s+([^\s\"',;}]+)", text, re.I):
        add("AUTHORIZATION", m.start(), m.end(), 90)
    for m in re.finditer(r"(?<![\w-])eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+(?![\w-])", text):
        add("JWT", m.start(), m.end(), 85)
    for m in re.finditer(r"(?<![\w-])(?:sk-(?:proj-)?[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9_]{16,}|github_pat_[A-Za-z0-9_]{16,}|xox[baprs]-[A-Za-z0-9-]{16,})(?![\w-])", text):
        add("API_KEY", m.start(), m.end(), 90)
    # 따옴표 값과 공백 없는 할당 값을 모두 지원한다. 키 이름은 남기고 값 구간만 가린다.
    assignments = r"\b(password|passwd|pwd|secret|api[_-]?key|access[_-]?token|refresh[_-]?token|token|authorization|cookie|set-cookie)\b[\"']?\s*[:=]\s*(?:\"([^\"\r\n]*)\"|'([^'\r\n]*)'|([^\s,;&}\]]+))"
    for m in re.finditer(assignments, text, re.I):
        # 그룹 2/3/4는 각각 큰따옴표/작은따옴표/따옴표 없는 값이다.
        group = next(i for i in (2, 3, 4) if m[i] is not None)
        key = m[1].lower()
        rule = "PASSWORD" if key in {"password", "passwd", "pwd"} else "AUTHORIZATION" if key in {"authorization", "cookie", "set-cookie"} else "API_KEY"
        if m[group]:
            add(rule, m.start(group), m.end(group), 90)
    return results
