from pathlib import Path
import argparse
import sqlite3


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "card_tracker.sqlite"


def main() -> None:
    parser = argparse.ArgumentParser(description="Search imported cards.")
    parser.add_argument("query", nargs="?", default="")
    parser.add_argument("--set-code", default="")
    parser.add_argument("--language", default="")
    args = parser.parse_args()

    like_query = f"%{args.query}%"

    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT
                COALESCE(sc.language, c.language) AS language,
                COALESCE(sc.set_name, c.set_name) AS set_name,
                COALESCE(sc.set_code, c.set_code) AS set_code,
                card_number,
                c.name,
                c.rarity,
                c.tcgcollector_card_id,
                c.card_detail_url,
                c.primary_image_path
            FROM cards c
            LEFT JOIN set_catalog sc ON sc.id = c.set_catalog_id
            WHERE
                (? = '' OR COALESCE(sc.set_code, c.set_code) = ?)
                AND (? = '' OR COALESCE(sc.language, c.language) = ?)
                AND (
                    ? = ''
                    OR c.card_number LIKE ?
                    OR c.name LIKE ?
                    OR c.rarity LIKE ?
                    OR COALESCE(sc.set_name, c.set_name) LIKE ?
                    OR COALESCE(sc.set_code, c.set_code) LIKE ?
                )
            ORDER BY language, set_name, c.card_number
            LIMIT 50
            """,
            (
                args.set_code,
                args.set_code,
                args.language,
                args.language,
                args.query,
                like_query,
                like_query,
                like_query,
                like_query,
                like_query,
            ),
        ).fetchall()

    for row in rows:
        print(" | ".join("" if value is None else str(value) for value in row))


if __name__ == "__main__":
    main()
