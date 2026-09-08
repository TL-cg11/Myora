"""검토 가능한 사전 JSON에서 MariaDB 초기 데이터 SQL을 생성한다."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def render_sql(rows):
    def quote(value):
        return "'" + value.replace("\\", "\\\\").replace("'", "''") + "'"
    values = ["(" + ", ".join(quote(row[key]) for key in ("category", "hanja", "name_ko", "meaning_ko")) + ")" for row in rows]
    return ("-- 원본: luck-was/app/data/saju_terms.json (korean-saju 0.3.0 기준)\n"
            "-- 재실행 시 이미 편집한 뜻을 덮어쓰지 않고 누락 항목만 추가한다.\n"
            "INSERT INTO saju_term (category, hanja, name_ko, meaning_ko) VALUES\n" + ",\n".join(values) +
            "\nON DUPLICATE KEY UPDATE id = saju_term.id;\n")


def render_narrative_sql(rows):
    def quote(value):
        return "'" + value.replace("\\", "\\\\").replace("'", "''") + "'"
    values = ["(" + ", ".join(quote(value) for value in
              (row['category'], row['hanja'], json.dumps(row['data'], ensure_ascii=False))) + ")" for row in rows]
    return ("-- 원본: luck-was/app/data/saju_narratives.json\n"
            "-- 일주 60종 + 용신 균형 5종 + 정격별 업무 조언 11종 + 신살 조언 29종\n"
            "-- 이미 편집한 상담 문구를 보존하고 누락 행만 추가한다.\n"
            "INSERT INTO saju_narrative_rule (category, hanja, data) VALUES\n" + ",\n".join(values) +
            "\nON DUPLICATE KEY UPDATE id = saju_narrative_rule.id;\n")


if __name__ == "__main__":
    rows = json.loads((ROOT / "app/data/saju_terms.json").read_text(encoding="utf-8"))
    target = ROOT.parent / "luck-mariadb/sql/init/13_saju_dictionary_seed.sql"
    target.write_text(render_sql(rows), encoding="utf-8")
    print(f"{len(rows)} dictionary entries exported to {target}")
    narrative_rows = json.loads((ROOT / "app/data/saju_narratives.json").read_text(encoding="utf-8"))
    narrative_target = ROOT.parent / "luck-mariadb/sql/init/15_saju_narrative_seed.sql"
    narrative_target.write_text(render_narrative_sql(narrative_rows), encoding="utf-8")
    print(f"{len(narrative_rows)} narrative rules exported to {narrative_target}")
