from pathlib import Path
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


def main() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    schema = SCHEMA_PATH.read_text(encoding="utf-8")

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(schema)
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
