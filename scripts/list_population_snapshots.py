from pathlib import Path
import argparse
import sqlite3


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "card_tracker.sqlite"


def main() -> None:
    parser = argparse.ArgumentParser(description="List grading population snapshots.")
    # Argument examples:
    #   Houndoom
    #   "Night Wanderer"
    #   omit query to list all snapshots
    parser.add_argument("query", nargs="?", default="")
    args = parser.parse_args()

    like_query = f"%{args.query}%"

    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT
                gps.grading_company,
                sc.language AS language,
                sc.set_name AS set_name,
                sc.set_code AS set_code,
                c.card_number,
                c.name,
                gps.snapshot_label,
                gps.population_total,
                gps.gem_threshold_grade,
                gps.gem_count,
                ROUND(gps.gem_rate * 100, 1) AS gem_rate_pct,
                gps.ten_plus_count,
                ROUND(gps.ten_plus_rate * 100, 1) AS ten_plus_rate_pct
            FROM grade_population_snapshots gps
            JOIN cards c ON c.id = gps.card_id
            JOIN set_catalog sc ON sc.id = c.set_catalog_id
            WHERE
                ? = ''
                OR c.name LIKE ?
                OR gps.snapshot_label LIKE ?
                OR sc.set_name LIKE ?
                OR sc.set_code LIKE ?
            ORDER BY
                gps.grading_company,
                language,
                set_name,
                c.card_number,
                gps.snapshot_label
            """,
            (args.query, like_query, like_query, like_query, like_query),
        ).fetchall()

    for row in rows:
        print(" | ".join("" if value is None else str(value) for value in row))


if __name__ == "__main__":
    main()
