# 개별 탐지 점수에서 로그 전체 위험도를 계산하는 중앙 정책.
from .models import Detection


# 탐지가 없으면 LOW/0, 있으면 최고 점수와 이름+생년월일 조합 정책을 적용한다.
def calculate_risk(detections: list[Detection]) -> tuple[str, int]:
    if not detections:
        return "LOW", 0
    score = max(d.risk_score for d in detections)
    rules = {d.rule_id for d in detections}
    # 이름과 생년월일이 함께 있으면 단일 정보보다 식별 위험이 커져 HIGH로 올린다.
    if {"PERSON_NAME", "BIRTH_DATE"} <= rules:
        score = max(score, 75)
    level = "CRITICAL" if score >= 95 else "HIGH" if score >= 75 else "MEDIUM" if score >= 50 else "LOW"
    return level, score
