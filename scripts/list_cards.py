from pathlib import Path
import sqlite3
import sys


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "card_tracker.sqlite"


def main() -> None:
    query = sys.argv[1] if len(sys.argv) > 1 else ""
    like_query = f"%{query}%"

    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT
                card_number,
                name,
                rarity,
                holo_pattern,
                primary_image_path
            FROM cards
            WHERE
                set_code = 'CBB5C'
                AND (
                    ? = ''
                    OR card_number LIKE ?
                    OR name LIKE ?
                    OR rarity LIKE ?
                    OR holo_pattern LIKE ?
                )
            ORDER BY card_number
            LIMIT 50
            """,
            (query, like_query, like_query, like_query, like_query),
        ).fetchall()

    for card_number, name, rarity, holo_pattern, image_path in rows:
        print(f"{card_number} | {name} | {rarity} | {holo_pattern} | {image_path}")


if __name__ == "__main__":
    main()
