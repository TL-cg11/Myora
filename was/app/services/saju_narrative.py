"""DB의 구조화된 상담 문구를 실제 계산값에 따라 조합한다. 무작위/LLM 생성 없음."""
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select, tuple_
from sqlalchemy.orm import Session

from app.models import SajuNarrativeRule
from app.services.saju_dictionary import MissingSajuTerm


class DayProfile(BaseModel):
    code: str = Field(min_length=1)
    keywords: list[str] = Field(min_length=1)
    strengths: list[str] = Field(min_length=1)
    weaknesses: list[str] = Field(min_length=1)
    career: list[str] = Field(min_length=1)
    relationship: list[str] = Field(min_length=1)
    intro: str = Field(min_length=1)
    strength_text: str = Field(min_length=1)
    caution_text: str = Field(min_length=1)
    career_text: str = Field(min_length=1)
    relationship_text: str = Field(min_length=1)
    branch_text: str = Field(min_length=1)
    subtitle: str = Field(min_length=1)


class Advice(BaseModel):
    text: str = Field(min_length=1)


def compose_saju_narrative(session: Session, interpretation: dict, time_unknown: bool) -> dict:
    day = next(p for p in interpretation['pillars'] if p['position'] == 'day')
    gyeok = interpretation['jeonggyeok']
    element = interpretation['yongsin']['element']
    # 일주에서 검출된 신살을 우선하며, 동일한 계산 결과는 항상 같은 순서로 해석한다.
    supporting = sorted(interpretation['sinsal'],
                        key=lambda item: (not any(loc in ('일지', '일간') for loc in item['locations']), item['term']['hanja']))[:2]
    keys = {('day', day['term']['hanja']), ('career', gyeok['hanja']), ('balance', element['hanja'])}
    keys.update(('support', item['term']['hanja']) for item in supporting)
    rows = session.scalars(select(SajuNarrativeRule).where(
        tuple_(SajuNarrativeRule.category, SajuNarrativeRule.hanja).in_(sorted(keys)))).all()
    rules = {(row.category, row.hanja): row.data for row in rows}
    if keys - rules.keys():
        raise MissingSajuTerm('사주 상담 데이터가 누락되었습니다. 상담 스키마와 초기 데이터(14, 15번 SQL)를 확인해 주세요.')
    try:
        profile = DayProfile.model_validate(rules['day', day['term']['hanja']])
        advice = {key: Advice.model_validate(value).text for key, value in rules.items() if key[0] != 'day'}
    except ValidationError as exc:
        raise MissingSajuTerm('사주 상담 데이터 형식이 올바르지 않습니다. 저장된 프로필과 조언을 확인해 주세요.') from exc

    return {
        'source': 'database',
        'version': 'narrative-v1',
        'title': f"{profile.code} 일주, 나의 기질을 읽어볼까요",
        'subtitle': profile.subtitle,
        'profile': profile.model_dump(),
        'overview': [profile.intro, profile.branch_text],
        'sections': [
            {'id': 'strengths', 'title': '이런 순간에 강점이 살아나요', 'keywords': profile.strengths,
             'paragraphs': [profile.strength_text]},
            {'id': 'caution', 'title': '이럴 때는 한 박자 쉬어가세요', 'keywords': profile.weaknesses,
             'paragraphs': [profile.caution_text]},
            {'id': 'career', 'title': '일과 성장에서는', 'keywords': profile.career,
             'paragraphs': [profile.career_text, f"{gyeok['name_ko']}으로 보는 이번 결과를 함께 살펴보면, " + advice['career', gyeok['hanja']]]},
            {'id': 'relationship', 'title': '사람과 마음을 나눌 때', 'keywords': profile.relationship,
             'paragraphs': [profile.relationship_text]},
            {'id': 'balance', 'title': '나에게 필요한 균형', 'keywords': [],
             'paragraphs': [f"이번 결과에서는 {element['name_ko']}의 기운이 균형을 돕는다고 보고 있어요. " + advice['balance', element['hanja']]]},
        ],
        'supporting': [{'name': item['term']['name_ko'], 'locations': item['locations'],
                       'text': advice['support', item['term']['hanja']]} for item in supporting],
        'notice': ('출생시간이 없어 기존 계산 기준인 정오를 사용한 참고 풀이예요. 실제 출생시간에 따라 결과가 달라질 수 있어요.'
                   if time_unknown else '양력 생년월일과 한국 표준시, 서울 경도를 기준으로 읽었어요.'),
    }
