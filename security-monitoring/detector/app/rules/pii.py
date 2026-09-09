# 개인정보 패턴 검사: 일치한 위치와 치환 문구를 반환하고 실제 치환은 masking에 맡긴다.
import re
from datetime import date

from ..models import Detection


# PII 공통 결과를 만든다. start는 포함, end는 제외하는 문자 위치다.
def finding(rule, start, end, replacement, score, confidence=0.95):
    level = "HIGH" if score >= 75 else "MEDIUM" if score >= 50 else "LOW"
    return Detection(rule, "PII", level, score, confidence, start, end, replacement)


# 텍스트에서 민감 패턴의 위치와 치환 정책을 수집한다.
def detect(text: str) -> list[Detection]:
    # 전화번호는 국번/자리 수를 확인하고, 일반 날짜는 생년월일 문맥이 있을 때만 탐지한다.
    results = []
    for m in re.finditer(r"(?<!\d)01[016789][- .]?\d{3,4}[- .]?\d{4}(?!\d)", text):
        digits = re.sub(r"\D", "", m[0])
        results.append(finding("PHONE_NUMBER", m.start(), m.end(),
                               f"{digits[:3]}-****-{digits[-4:]}", 50))
    for m in re.finditer(r"(?<![\w.+-])[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+", text):
        local, domain = m[0].split("@", 1)
        results.append(finding("EMAIL_ADDRESS", m.start(), m.end(), f"{local[0]}***@{domain}", 30))
    # 주민번호는 날짜가 가능한 후보를 마스킹한다. 체크섬 실패로 노출을 허용하지 않는다.
    for m in re.finditer(r"(?<!\d)(\d{6})[- ]?([1-8]\d{6})(?!\d)", text):
        digits = m[1]
        century = 1900 if m[2][0] in "1256" else 2000
        try:
            date(century + int(digits[:2]), int(digits[2:4]), int(digits[4:]))
        except ValueError:
            continue
        results.append(finding("KR_RRN", m.start(), m.end(), "[REDACTED_RRN]", 85, 0.9))
    for m in re.finditer(r"(?:생년월일|birth_date|birthdate|date_of_birth|dob)\s*[\"']?\s*[:=은는]?\s*[\"']?(\d{4}[-./]\d{2}[-./]\d{2}|\d{8})", text, re.I):
        results.append(finding("BIRTH_DATE", m.start(1), m.end(1), "[REDACTED_BIRTH_DATE]", 50))
    # Free-text names require a separate evaluated recognizer. Structured fields
    # are handled unconditionally in the engine.
    return results
