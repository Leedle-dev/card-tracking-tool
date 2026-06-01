from pathlib import Path
import argparse
import sqlite3


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "card_tracker.sqlite"


def money(cents: int) -> str:
    return f"${cents / 100:.2f}"


def main() -> None:
    parser = argparse.ArgumentParser(description="List raw and graded price records.")
    # Argument examples:
    #   Houndoom
    #   "Shrouded Fable"
    #   omit query to list all price records
    parser.add_argument("query", nargs="?", default="")
    args = parser.parse_args()

    like_query = f"%{args.query}%"

    with sqlite3.connect(DB_PATH) as conn:
        raw_rows = conn.execute(
            """
            SELECT
                'RAW',
                sc.language,
                sc.set_name,
                sc.set_code,
                c.card_number,
                c.name,
                ms.name,
                r.checked_at,
                r.listing_type,
                r.condition,
                r.price_cents,
                r.notes
            FROM raw_price_records r
            JOIN cards c ON c.id = r.card_id
            JOIN set_catalog sc ON sc.id = c.set_catalog_id
            JOIN marketplace_sources ms ON ms.id = r.source_id
            WHERE
                ? = ''
                OR c.name LIKE ?
                OR sc.set_name LIKE ?
                OR sc.set_code LIKE ?
                OR r.notes LIKE ?
            ORDER BY r.checked_at DESC, c.name
            """,
            (args.query, like_query, like_query, like_query, like_query),
        ).fetchall()
        graded_rows = conn.execute(
            """
            SELECT
                'GRADED',
                sc.language,
                sc.set_name,
                sc.set_code,
                c.card_number,
                c.name,
                ms.name,
                g.checked_at,
                g.listing_type,
                g.grading_company || ' ' || g.grade,
                g.price_cents,
                g.notes
            FROM graded_price_records g
            JOIN cards c ON c.id = g.card_id
            JOIN set_catalog sc ON sc.id = c.set_catalog_id
            JOIN marketplace_sources ms ON ms.id = g.source_id
            WHERE
                ? = ''
                OR c.name LIKE ?
                OR sc.set_name LIKE ?
                OR sc.set_code LIKE ?
                OR g.notes LIKE ?
            ORDER BY g.checked_at DESC, c.name, g.grading_company, g.grade
            """,
            (args.query, like_query, like_query, like_query, like_query),
        ).fetchall()

    for row in raw_rows + graded_rows:
        print(
            " | ".join(
                "" if value is None else money(value) if index == 10 else str(value)
                for index, value in enumerate(row)
            )
        )


if __name__ == "__main__":
    main()
