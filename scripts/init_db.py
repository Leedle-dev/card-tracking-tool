from pathlib import Path
from datetime import datetime
import sqlite3


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "card_tracker.sqlite"
SCHEMA_PATH = ROOT / "db" / "schema.sql"

SOURCES = [
    ("eBay", "https://www.ebay.com", "Marketplace pricing source."),
    ("TCGplayer", "https://www.tcgplayer.com", "Trading card marketplace pricing source."),
    ("CardTrader", "https://www.cardtrader.com", "International card marketplace pricing source."),
    ("Manual Comp", None, "Manually entered comparable sale or listing."),
]

GRADING_PROFILES = [
    (
        "PSA Standard Placeholder",
        "PSA",
        "Standard",
        2500,
        500,
        500,
        0.13,
        "Placeholder fee profile. Update before relying on EV results.",
    ),
]


LANGUAGE_BY_REGION = {
    "international": "English",
    "japanese": "Japanese",
    "s-chinese": "Simplified Chinese",
}


def table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def column_names(conn: sqlite3.Connection, table_name: str) -> set[str]:
    if not table_exists(conn, table_name):
        return set()
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table_name})")}


def parse_release_year(release_date_text: str | None) -> int | None:
    if not release_date_text:
        return None
    try:
        return datetime.strptime(release_date_text, "%b %d, %Y").year
    except ValueError:
        return None


def pre_schema_migrations(conn: sqlite3.Connection) -> None:
    card_columns = column_names(conn, "cards")
    card_columns_to_add = {
        "set_catalog_id": "INTEGER",
        "pokedex_id": "INTEGER",
    }
    for column, column_type in card_columns_to_add.items():
        if card_columns and column not in card_columns:
            conn.execute(f"ALTER TABLE cards ADD COLUMN {column} {column_type}")

    set_catalog_columns = column_names(conn, "set_catalog")
    set_catalog_columns_to_add = {
        "language": "TEXT",
        "release_year": "INTEGER",
    }
    for column, column_type in set_catalog_columns_to_add.items():
        if set_catalog_columns and column not in set_catalog_columns:
            conn.execute(f"ALTER TABLE set_catalog ADD COLUMN {column} {column_type}")


def backfill_set_catalog(conn: sqlite3.Connection) -> None:
    if not table_exists(conn, "set_catalog"):
        return

    rows = conn.execute(
        """
        SELECT id, source_region, release_date_text
        FROM set_catalog
        WHERE language IS NULL OR release_year IS NULL
        """
    ).fetchall()
    for row_id, source_region, release_date_text in rows:
        conn.execute(
            """
            UPDATE set_catalog
            SET
                language = COALESCE(language, ?),
                release_year = COALESCE(release_year, ?)
            WHERE id = ?
            """,
            (
                LANGUAGE_BY_REGION.get(source_region),
                parse_release_year(release_date_text),
                row_id,
            ),
        )


def backfill_card_set_catalog_links(conn: sqlite3.Connection) -> None:
    if not table_exists(conn, "cards") or not table_exists(conn, "set_catalog"):
        return

    rows = conn.execute(
        """
        SELECT id, set_code, set_name, language
        FROM cards
        WHERE set_catalog_id IS NULL
        """
    ).fetchall()

    for card_id, set_code, set_name, language in rows:
        match = conn.execute(
            """
            SELECT id
            FROM set_catalog
            WHERE
                (
                    set_code IS NOT NULL
                    AND ? IS NOT NULL
                    AND set_code = ?
                )
                OR (
                    lower(set_name) = lower(?)
                    AND language = ?
                )
            ORDER BY
                CASE WHEN set_code = ? THEN 0 ELSE 1 END,
                id
            LIMIT 1
            """,
            (set_code, set_code, set_name, language, set_code),
        ).fetchone()
        if match:
            conn.execute(
                "UPDATE cards SET set_catalog_id = ? WHERE id = ?",
                (match[0], card_id),
            )


def main() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    schema = SCHEMA_PATH.read_text(encoding="utf-8")

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        pre_schema_migrations(conn)
        conn.executescript(schema)
        backfill_set_catalog(conn)
        backfill_card_set_catalog_links(conn)
        conn.executemany(
            """
            INSERT INTO marketplace_sources (name, website_url, notes)
            VALUES (?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                website_url = excluded.website_url,
                notes = excluded.notes
            """,
            SOURCES,
        )
        conn.executemany(
            """
            INSERT INTO grading_profiles (
                name,
                grading_company,
                service_level,
                grading_fee_cents,
                inbound_shipping_cents,
                return_shipping_cents,
                marketplace_fee_rate,
                notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(name) DO NOTHING
            """,
            GRADING_PROFILES,
        )

    print(f"Database initialized at {DB_PATH}")


if __name__ == "__main__":
    main()
