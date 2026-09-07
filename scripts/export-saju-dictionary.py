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


if __name__ == "__main__":
    rows = json.loads((ROOT / "app/data/saju_terms.json").read_text(encoding="utf-8"))
    target = ROOT.parent / "luck-mariadb/sql/init/13_saju_dictionary_seed.sql"
    target.write_text(render_sql(rows), encoding="utf-8")
    print(f"{len(rows)} dictionary entries exported to {target}")
