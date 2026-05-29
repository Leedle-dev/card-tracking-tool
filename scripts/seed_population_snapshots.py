from pathlib import Path
import sqlite3


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "card_tracker.sqlite"


SNAPSHOTS = [
    {
        "card": {
            "language": "English",
            "set_code": "SFA",
            "card_number": "066/064",
            "name": "Houndoom",
        },
        "grading_company": "BGS",
        "source_name": "GemRate public Beckett table",
        "source_url": None,
        "snapshot_label": "English Houndoom Shrouded Fable 066 BGS pop",
        "checked_at": "2026-05-28",
        "population_total": 140,
        "gem_threshold_grade": "BGS 9.5+",
        "gem_count": 48,
        "gem_rate": 0.343,
        "ten_plus_count": 2,
        "ten_plus_rate": 0.014,
        "exact_card_data": 1,
        "notes": "Beckett gem rate is BGS 9.5 or higher.",
        "rows": [
            ("BGS 7", 0, 0.0, 139, 0.993),
            ("BGS 7.5", 0, 0.0, 139, 0.993),
            ("BGS 8", 0, 0.0, 139, 0.993),
            ("BGS 8.5", 19, 0.136, 120, 0.857),
            ("BGS 9", 72, 0.514, 48, 0.343),
            ("BGS 9.5", 46, 0.329, 2, 0.014),
            ("BGS 10 Pristine", 2, 0.014, 0, 0.0),
            ("BGS 10 Black Label", 0, 0.0, None, None),
        ],
    },
    {
        "card": {
            "language": "Japanese",
            "set_code": "SV6a",
            "card_number": "066/064",
            "name": "Houndoom",
        },
        "grading_company": "BGS",
        "source_name": "GemRate public Beckett table",
        "source_url": None,
        "snapshot_label": "Japanese Houndoom Night Wanderer 066 BGS pop",
        "checked_at": "2026-05-28",
        "population_total": 105,
        "gem_threshold_grade": "BGS 9.5+",
        "gem_count": 98,
        "gem_rate": 0.933,
        "ten_plus_count": 21,
        "ten_plus_rate": 0.20,
        "exact_card_data": 1,
        "notes": "Useful Japanese-print prior for sparse Simplified Chinese population data.",
        "rows": [
            ("BGS 7", 0, 0.0, 105, 1.0),
            ("BGS 7.5", 1, 0.01, 104, 0.99),
            ("BGS 8", 0, 0.0, 104, 0.99),
            ("BGS 8.5", 0, 0.0, 104, 0.99),
            ("BGS 9", 6, 0.057, 98, 0.933),
            ("BGS 9.5", 77, 0.733, 21, 0.20),
            ("BGS 10 Pristine", 19, 0.181, 2, 0.019),
            ("BGS 10 Black Label", 2, 0.019, None, None),
        ],
    },
    {
        "card": {
            "language": "Japanese",
            "set_code": "SV2a",
            "card_number": "173/165",
            "name": "Pikachu",
            "rarity": "Art Rare",
        },
        "grading_company": "BGS",
        "source_name": "GemRate public Beckett table",
        "source_url": None,
        "snapshot_label": "Japanese 151 Pikachu AR 173 BGS benchmark",
        "checked_at": "2026-05-28",
        "population_total": 1642,
        "gem_threshold_grade": "BGS 9.5+",
        "gem_count": 1431,
        "gem_rate": 0.871,
        "ten_plus_count": 357,
        "ten_plus_rate": 0.217,
        "exact_card_data": 1,
        "notes": "High-population Japanese modern print benchmark.",
        "rows": [
            ("BGS 7", 3, 0.002, 1638, 0.997),
            ("BGS 7.5", 1, 0.001, 1637, 0.996),
            ("BGS 8", 4, 0.002, 1633, 0.994),
            ("BGS 8.5", 17, 0.01, 1610, 0.984),
            ("BGS 9", 184, 0.112, 1431, 0.871),
            ("BGS 9.5", 1074, 0.654, 357, 0.217),
            ("BGS 10 Pristine", 316, 0.192, 41, 0.025),
            ("BGS 10 Black Label", 41, 0.025, None, None),
        ],
    },
    {
        "card": {
            "language": "Japanese",
            "set_code": "SV2a",
            "card_number": "025/165",
            "name": "Pikachu",
            "variant_hint": "Master Ball Reverse Holo C",
        },
        "grading_company": "BGS",
        "source_name": "GemRate public Beckett table",
        "source_url": None,
        "snapshot_label": "Japanese 151 Pikachu Master Ball Reverse Holo 025 BGS benchmark",
        "checked_at": "2026-05-28",
        "population_total": 536,
        "gem_threshold_grade": "BGS 9.5+",
        "gem_count": 488,
        "gem_rate": 0.91,
        "ten_plus_count": 134,
        "ten_plus_rate": 0.25,
        "exact_card_data": 1,
        "notes": "High-population Japanese modern Master Ball reverse benchmark.",
        "rows": [
            ("BGS 7", 0, 0.0, 536, 1.0),
            ("BGS 7.5", 0, 0.0, 536, 1.0),
            ("BGS 8", 2, 0.004, 534, 0.996),
            ("BGS 8.5", 4, 0.007, 530, 0.989),
            ("BGS 9", 42, 0.078, 488, 0.91),
            ("BGS 9.5", 354, 0.66, 134, 0.25),
            ("BGS 10 Pristine", 121, 0.226, 13, 0.024),
            ("BGS 10 Black Label", 13, 0.024, None, None),
        ],
    },
]


def find_card(conn: sqlite3.Connection, criteria: dict[str, str]) -> int:
    rows = conn.execute(
        """
        SELECT
            c.id,
            sc.language AS language,
            sc.set_code AS set_code,
            c.card_number,
            c.name,
            c.rarity,
            c.tcgcollector_card_id
        FROM cards c
        JOIN set_catalog sc ON sc.id = c.set_catalog_id
        WHERE
            sc.language = ?
            AND sc.set_code = ?
            AND c.card_number = ?
            AND c.name = ?
        ORDER BY
            CASE
                WHEN ? IS NOT NULL AND c.rarity = ? THEN 0
                WHEN ? IS NOT NULL AND c.rarity LIKE '%' || ? || '%' THEN 1
                ELSE 2
            END,
            c.tcgcollector_card_id
        """,
        (
            criteria["language"],
            criteria["set_code"],
            criteria["card_number"],
            criteria["name"],
            criteria.get("rarity"),
            criteria.get("rarity"),
            criteria.get("rarity"),
            criteria.get("rarity"),
        ),
    ).fetchall()
    if not rows:
        raise SystemExit(
            "Card not found for population snapshot: "
            f"{criteria['language']} {criteria['set_code']} "
            f"{criteria['card_number']} {criteria['name']}. "
            "Import the set first if needed."
        )
    if len(rows) > 1 and not criteria.get("variant_hint"):
        matches = "\n".join(str(row) for row in rows)
        raise SystemExit(f"Ambiguous card match for {criteria}: \n{matches}")
    return rows[0][0]


def upsert_snapshot(conn: sqlite3.Connection, snapshot: dict[str, object]) -> int:
    card_id = find_card(conn, snapshot["card"])
    conn.execute(
        """
        INSERT INTO grade_population_snapshots (
            card_id,
            grading_company,
            source_name,
            source_url,
            snapshot_label,
            checked_at,
            population_total,
            gem_threshold_grade,
            gem_count,
            gem_rate,
            ten_plus_count,
            ten_plus_rate,
            exact_card_data,
            notes
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(card_id, grading_company, source_name, snapshot_label, checked_at)
        DO UPDATE SET
            source_url = excluded.source_url,
            population_total = excluded.population_total,
            gem_threshold_grade = excluded.gem_threshold_grade,
            gem_count = excluded.gem_count,
            gem_rate = excluded.gem_rate,
            ten_plus_count = excluded.ten_plus_count,
            ten_plus_rate = excluded.ten_plus_rate,
            exact_card_data = excluded.exact_card_data,
            notes = excluded.notes
        """,
        (
            card_id,
            snapshot["grading_company"],
            snapshot["source_name"],
            snapshot["source_url"],
            snapshot["snapshot_label"],
            snapshot["checked_at"],
            snapshot["population_total"],
            snapshot["gem_threshold_grade"],
            snapshot["gem_count"],
            snapshot["gem_rate"],
            snapshot["ten_plus_count"],
            snapshot["ten_plus_rate"],
            snapshot["exact_card_data"],
            snapshot["notes"],
        ),
    )
    snapshot_id = conn.execute(
        """
        SELECT id
        FROM grade_population_snapshots
        WHERE card_id = ?
          AND grading_company = ?
          AND source_name = ?
          AND snapshot_label = ?
          AND checked_at = ?
        """,
        (
            card_id,
            snapshot["grading_company"],
            snapshot["source_name"],
            snapshot["snapshot_label"],
            snapshot["checked_at"],
        ),
    ).fetchone()[0]
    conn.execute(
        "DELETE FROM grade_population_snapshot_rows WHERE snapshot_id = ?",
        (snapshot_id,),
    )
    conn.executemany(
        """
        INSERT INTO grade_population_snapshot_rows (
            snapshot_id,
            grade_label,
            population_count,
            rate,
            higher_count,
            higher_rate
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            (snapshot_id, grade_label, count, rate, higher_count, higher_rate)
            for grade_label, count, rate, higher_count, higher_rate in snapshot["rows"]
        ],
    )
    return snapshot_id


def main() -> None:
    if not DB_PATH.exists():
        raise SystemExit(f"Database not found: {DB_PATH}. Run scripts/init_db.py first.")

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        snapshot_ids = [upsert_snapshot(conn, snapshot) for snapshot in SNAPSHOTS]

    print(f"Seeded {len(snapshot_ids)} population snapshots into {DB_PATH}")


if __name__ == "__main__":
    main()
