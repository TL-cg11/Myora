"""계산 엔진에서는 식별자만 가져오고, 이름과 뜻은 매 요청 DB에서 조회한다."""
from sqlalchemy import select, tuple_
from sqlalchemy.orm import Session

from app.models import SajuTerm


class MissingSajuTerm(ValueError):
    pass


def lookup_saju_meanings(session: Session, saju, analysis) -> dict:
    pillars = [(key, getattr(saju, f"{key}_pillar")) for key in ("year", "month", "day", "hour")]
    gyeok = analysis.jeonggyeok.gyeokguk
    yong = analysis.yongsin
    detections = analysis.sinsal
    concept_keys = ["年柱", "月柱", "日柱", "時柱", "日干", "正格", "用神", "神殺"]
    keys = {("concept", hanja) for hanja in concept_keys}
    keys.update({("gyeokguk", gyeok.hanja), ("element", yong.yong_o_haeng.hanja),
                 ("yongsin_method", yong.method.hanja)})
    if yong.bo_o_haeng is not None:
        keys.add(("element", yong.bo_o_haeng.hanja))
    if yong.bo_method is not None:
        keys.add(("yongsin_method", yong.bo_method.hanja))
    for _, pillar in pillars:
        if pillar is not None:
            keys.update({("ganji", pillar.hanja), ("stem", pillar.cheon_gan.hanja), ("branch", pillar.ji_ji.hanja)})
    keys.update(("sinsal", item.sinsal.hanja) for item in detections)
    rows = session.scalars(select(SajuTerm).where(tuple_(SajuTerm.category, SajuTerm.hanja).in_(sorted(keys)))).all()
    terms = {(row.category, row.hanja): {"category": row.category, "hanja": row.hanja,
             "name_ko": row.name_ko, "meaning_ko": row.meaning_ko} for row in rows}
    missing = keys - terms.keys()
    if missing:
        raise MissingSajuTerm("사주 사전 데이터가 누락되었습니다: " + ", ".join(f"{category}/{hanja}" for category, hanja in sorted(missing)))

    def term(category, hanja):
        return terms[category, hanja]

    return {
        "source": "database",
        "concepts": {hanja: term("concept", hanja) for hanja in concept_keys},
        "pillars": [{"position": position, "term": term("ganji", pillar.hanja),
                     "stem": term("stem", pillar.cheon_gan.hanja), "branch": term("branch", pillar.ji_ji.hanja)}
                    for position, pillar in pillars if pillar is not None],
        "day_stem": term("stem", saju.day_stem.hanja),
        "jeonggyeok": term("gyeokguk", gyeok.hanja),
        "yongsin": {"element": term("element", yong.yong_o_haeng.hanja),
                    "method": term("yongsin_method", yong.method.hanja),
                    "auxiliary_element": term("element", yong.bo_o_haeng.hanja) if yong.bo_o_haeng else None,
                    "auxiliary_method": term("yongsin_method", yong.bo_method.hanja) if yong.bo_method else None},
        "sinsal": [{"term": term("sinsal", item.sinsal.hanja), "locations": [location.label for location in item.locations]}
                   for item in detections],
    }
