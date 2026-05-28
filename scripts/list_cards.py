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
                language,
                set_name,
                set_code,
                card_number,
                name,
                rarity,
                tcgcollector_card_id,
                card_detail_url,
                primary_image_path
            FROM cards
            WHERE
                (? = '' OR set_code = ?)
                AND (? = '' OR language = ?)
                AND (
                    ? = ''
                    OR card_number LIKE ?
                    OR name LIKE ?
                    OR rarity LIKE ?
                    OR set_name LIKE ?
                    OR set_code LIKE ?
                )
            ORDER BY language, set_name, card_number
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
