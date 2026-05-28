from pathlib import Path
import csv
from datetime import datetime
import sqlite3


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "card_tracker.sqlite"
TSV_PATH = ROOT / "data" / "raw_fetches" / "tcgcollector_sets_all.tsv"

CATALOG_URLS = {
    "international": "https://www.tcgcollector.com/sets/intl",
    "japanese": "https://www.tcgcollector.com/sets/jp",
    "s-chinese": "https://www.tcgcollector.com/sets/cn",
}

LANGUAGE_BY_REGION = {
    "international": "English",
    "japanese": "Japanese",
    "s-chinese": "Simplified Chinese",
}


def parse_int(value: str) -> int | None:
    value = value.strip()
    return int(value) if value else None


def parse_release_year(value: str) -> int | None:
    value = value.strip()
    if not value:
        return None
    try:
        return datetime.strptime(value, "%b %d, %Y").year
    except ValueError:
        return None


def load_rows() -> list[dict[str, str]]:
    if not TSV_PATH.exists():
        raise SystemExit(
            f"Set catalog TSV not found: {TSV_PATH}. "
            "Run scripts/fetch_tcgcollector_sets.py first."
        )

    with TSV_PATH.open("r", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file, delimiter="\t"))


def ensure_schema_columns(conn: sqlite3.Connection) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(set_catalog)").fetchall()}
    columns_to_add = {
        "language": "TEXT",
        "release_year": "INTEGER",
    }
    for column, column_type in columns_to_add.items():
        if column not in columns:
            conn.execute(f"ALTER TABLE set_catalog ADD COLUMN {column} {column_type}")


def import_rows(rows: list[dict[str, str]]) -> None:
    if not DB_PATH.exists():
        raise SystemExit(f"Database not found: {DB_PATH}. Run scripts/init_db.py first.")

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        ensure_schema_columns(conn)
        conn.executemany(
            """
            INSERT INTO set_catalog (
                source_name,
                source_region,
                language,
                tcgcollector_set_id,
                set_name,
                set_code,
                release_date_text,
                release_year,
                card_count,
                set_url,
                slug,
                source_catalog_url,
                last_seen_at
            )
            VALUES (
                'TCGcollector',
                :source_region,
                :language,
                :tcgcollector_set_id,
                :set_name,
                :set_code,
                :release_date_text,
                :release_year,
                :card_count,
                :set_url,
                :slug,
                :source_catalog_url,
                CURRENT_TIMESTAMP
            )
            ON CONFLICT(source_name, source_region, tcgcollector_set_id)
            DO UPDATE SET
                set_name = excluded.set_name,
                set_code = excluded.set_code,
                language = excluded.language,
                release_date_text = excluded.release_date_text,
                release_year = excluded.release_year,
                card_count = excluded.card_count,
                set_url = excluded.set_url,
                slug = excluded.slug,
                source_catalog_url = excluded.source_catalog_url,
                last_seen_at = CURRENT_TIMESTAMP
            """,
            [
                {
                    "source_region": row["source_region"],
                    "language": LANGUAGE_BY_REGION.get(row["source_region"]),
                    "tcgcollector_set_id": parse_int(row["tcgcollector_set_id"]),
                    "set_name": row["set_name"],
                    "set_code": row["set_code"] or None,
                    "release_date_text": row["release_date_text"] or None,
                    "release_year": parse_release_year(row["release_date_text"]),
                    "card_count": parse_int(row["card_count"]),
                    "set_url": row["set_url"],
                    "slug": row["slug"] or None,
                    "source_catalog_url": CATALOG_URLS.get(row["source_region"]),
                }
                for row in rows
            ],
        )


def main() -> None:
    rows = load_rows()
    import_rows(rows)
    print(f"Imported {len(rows)} TCGcollector set catalog rows into {DB_PATH}")


if __name__ == "__main__":
    main()
