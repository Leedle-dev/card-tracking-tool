from pathlib import Path
import sqlite3


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "card_tracker.sqlite"
SEED_NOTE_PREFIX = "Seeded example Houndoom pricing"


PRICECHARTING_URLS = {
    "english_houndoom": "https://www.pricecharting.com/game/pokemon-shrouded-fable/houndoom-66",
    "japanese_houndoom": "https://www.pricecharting.com/game/pokemon-japanese-night-wanderer/houndoom-66",
}


RAW_PRICE_RECORDS = [
    {
        "card": {
            "language": "English",
            "set_code": "SFA",
            "card_number": "066/064",
            "name": "Houndoom",
        },
        "source": "PriceCharting",
        "checked_at": "2026-05-28",
        "listing_type": "price_guide_estimate",
        "price_cents": 4000,
        "condition": "Ungraded",
        "listing_url": PRICECHARTING_URLS["english_houndoom"],
        "notes": (
            f"{SEED_NOTE_PREFIX}: PriceCharting ungraded guide estimate. "
            "Page showed ungraded $40.00."
        ),
    },
    {
        "card": {
            "language": "Japanese",
            "set_code": "SV6a",
            "card_number": "066/064",
            "name": "Houndoom",
        },
        "source": "PriceCharting",
        "checked_at": "2026-05-28",
        "listing_type": "price_guide_estimate",
        "price_cents": 800,
        "condition": "Ungraded",
        "listing_url": PRICECHARTING_URLS["japanese_houndoom"],
        "notes": (
            f"{SEED_NOTE_PREFIX}: PriceCharting ungraded guide estimate. "
            "Page showed ungraded $8.00."
        ),
    },
]


GRADED_PRICE_RECORDS = [
    {
        "card": {
            "language": "English",
            "set_code": "SFA",
            "card_number": "066/064",
            "name": "Houndoom",
        },
        "source": "eBay",
        "checked_at": "2025-06-11",
        "grading_company": "BGS",
        "grade": "9.5",
        "listing_type": "sold_comp_verified_title",
        "price_cents": 7999,
        "listing_url": PRICECHARTING_URLS["english_houndoom"],
        "seller_name": "eBay via PriceCharting",
        "notes": (
            f"{SEED_NOTE_PREFIX}: Title explicitly said BGS 9.5 Gem Mint. "
            "Do not substitute PriceCharting's mixed Grade 9.5 bucket for BGS 9.5."
        ),
    },
    {
        "card": {
            "language": "English",
            "set_code": "SFA",
            "card_number": "066/064",
            "name": "Houndoom",
        },
        "source": "PriceCharting",
        "checked_at": "2026-05-28",
        "grading_company": "PSA",
        "grade": "10",
        "listing_type": "price_guide_estimate",
        "price_cents": 20375,
        "listing_url": PRICECHARTING_URLS["english_houndoom"],
        "seller_name": "PriceCharting",
        "notes": f"{SEED_NOTE_PREFIX}: PriceCharting PSA 10 guide estimate.",
    },
    {
        "card": {
            "language": "English",
            "set_code": "SFA",
            "card_number": "066/064",
            "name": "Houndoom",
        },
        "source": "PriceCharting",
        "checked_at": "2026-05-28",
        "grading_company": "CGC",
        "grade": "10",
        "listing_type": "price_guide_estimate",
        "price_cents": 6599,
        "listing_url": PRICECHARTING_URLS["english_houndoom"],
        "seller_name": "PriceCharting",
        "notes": f"{SEED_NOTE_PREFIX}: PriceCharting CGC 10 guide estimate.",
    },
    {
        "card": {
            "language": "English",
            "set_code": "SFA",
            "card_number": "066/064",
            "name": "Houndoom",
        },
        "source": "PriceCharting",
        "checked_at": "2026-05-28",
        "grading_company": "CGC",
        "grade": "10 Pristine",
        "listing_type": "price_guide_estimate",
        "price_cents": 32500,
        "listing_url": PRICECHARTING_URLS["english_houndoom"],
        "seller_name": "PriceCharting",
        "notes": f"{SEED_NOTE_PREFIX}: PriceCharting CGC 10 Pristine guide estimate.",
    },
    {
        "card": {
            "language": "English",
            "set_code": "SFA",
            "card_number": "066/064",
            "name": "Houndoom",
        },
        "source": "PriceCharting",
        "checked_at": "2026-05-28",
        "grading_company": "BGS",
        "grade": "10 Pristine",
        "listing_type": "price_guide_estimate_low_confidence",
        "price_cents": 26500,
        "listing_url": PRICECHARTING_URLS["english_houndoom"],
        "seller_name": "PriceCharting",
        "notes": (
            f"{SEED_NOTE_PREFIX}: PriceCharting BGS 10 guide estimate. "
            "Page showed BGS 10 sold listing count as 0, so confidence is low."
        ),
    },
    {
        "card": {
            "language": "English",
            "set_code": "SFA",
            "card_number": "066/064",
            "name": "Houndoom",
        },
        "source": "PriceCharting",
        "checked_at": "2026-05-28",
        "grading_company": "BGS",
        "grade": "10 Black Label",
        "listing_type": "price_guide_estimate_low_confidence",
        "price_cents": 132500,
        "listing_url": PRICECHARTING_URLS["english_houndoom"],
        "seller_name": "PriceCharting",
        "notes": (
            f"{SEED_NOTE_PREFIX}: PriceCharting BGS 10 Black guide estimate. "
            "Page showed BGS 10 Black sold listing count as 0, so confidence is low."
        ),
    },
    {
        "card": {
            "language": "Japanese",
            "set_code": "SV6a",
            "card_number": "066/064",
            "name": "Houndoom",
        },
        "source": "eBay",
        "checked_at": "2026-04-09",
        "grading_company": "BGS",
        "grade": "9.5",
        "listing_type": "sold_comp_verified_title",
        "price_cents": 2399,
        "listing_url": PRICECHARTING_URLS["japanese_houndoom"],
        "seller_name": "eBay via PriceCharting",
        "notes": (
            f"{SEED_NOTE_PREFIX}: Title explicitly said BGS 9.5 Gem. "
            "PriceCharting's Grade 9.5 bucket also contains CGC/SGC 9.5."
        ),
    },
    {
        "card": {
            "language": "Japanese",
            "set_code": "SV6a",
            "card_number": "066/064",
            "name": "Houndoom",
        },
        "source": "eBay",
        "checked_at": "2025-04-15",
        "grading_company": "BGS",
        "grade": "9.5",
        "listing_type": "sold_comp_verified_title",
        "price_cents": 1626,
        "listing_url": PRICECHARTING_URLS["japanese_houndoom"],
        "seller_name": "eBay via PriceCharting",
        "notes": f"{SEED_NOTE_PREFIX}: Title explicitly said BGS 9.5.",
    },
    {
        "card": {
            "language": "Japanese",
            "set_code": "SV6a",
            "card_number": "066/064",
            "name": "Houndoom",
        },
        "source": "PriceCharting",
        "checked_at": "2026-05-28",
        "grading_company": "PSA",
        "grade": "10",
        "listing_type": "price_guide_estimate",
        "price_cents": 4108,
        "listing_url": PRICECHARTING_URLS["japanese_houndoom"],
        "seller_name": "PriceCharting",
        "notes": f"{SEED_NOTE_PREFIX}: PriceCharting PSA 10 guide estimate.",
    },
    {
        "card": {
            "language": "Japanese",
            "set_code": "SV6a",
            "card_number": "066/064",
            "name": "Houndoom",
        },
        "source": "PriceCharting",
        "checked_at": "2026-05-28",
        "grading_company": "CGC",
        "grade": "10",
        "listing_type": "price_guide_estimate",
        "price_cents": 2799,
        "listing_url": PRICECHARTING_URLS["japanese_houndoom"],
        "seller_name": "PriceCharting",
        "notes": f"{SEED_NOTE_PREFIX}: PriceCharting CGC 10 guide estimate.",
    },
    {
        "card": {
            "language": "Japanese",
            "set_code": "SV6a",
            "card_number": "066/064",
            "name": "Houndoom",
        },
        "source": "PriceCharting",
        "checked_at": "2026-05-28",
        "grading_company": "CGC",
        "grade": "10 Pristine",
        "listing_type": "price_guide_estimate",
        "price_cents": 4044,
        "listing_url": PRICECHARTING_URLS["japanese_houndoom"],
        "seller_name": "PriceCharting",
        "notes": f"{SEED_NOTE_PREFIX}: PriceCharting CGC 10 Pristine guide estimate.",
    },
    {
        "card": {
            "language": "Japanese",
            "set_code": "SV6a",
            "card_number": "066/064",
            "name": "Houndoom",
        },
        "source": "PriceCharting",
        "checked_at": "2026-05-28",
        "grading_company": "BGS",
        "grade": "10 Pristine",
        "listing_type": "price_guide_estimate",
        "price_cents": 3637,
        "listing_url": PRICECHARTING_URLS["japanese_houndoom"],
        "seller_name": "PriceCharting",
        "notes": f"{SEED_NOTE_PREFIX}: PriceCharting BGS 10 guide estimate.",
    },
    {
        "card": {
            "language": "Japanese",
            "set_code": "SV6a",
            "card_number": "066/064",
            "name": "Houndoom",
        },
        "source": "PriceCharting",
        "checked_at": "2026-05-28",
        "grading_company": "BGS",
        "grade": "10 Black Label",
        "listing_type": "price_guide_estimate",
        "price_cents": 30600,
        "listing_url": PRICECHARTING_URLS["japanese_houndoom"],
        "seller_name": "PriceCharting",
        "notes": f"{SEED_NOTE_PREFIX}: PriceCharting BGS 10 Black guide estimate.",
    },
]


def source_id(conn: sqlite3.Connection, source_name: str) -> int:
    row = conn.execute(
        "SELECT id FROM marketplace_sources WHERE name = ?",
        (source_name,),
    ).fetchone()
    if not row:
        raise SystemExit(f"Marketplace source not found: {source_name}. Run scripts/init_db.py first.")
    return row[0]


def find_card(conn: sqlite3.Connection, criteria: dict[str, str]) -> int:
    row = conn.execute(
        """
        SELECT c.id
        FROM cards c
        LEFT JOIN set_catalog sc ON sc.id = c.set_catalog_id
        WHERE
            COALESCE(sc.language, c.language) = ?
            AND COALESCE(sc.set_code, c.set_code) = ?
            AND c.card_number = ?
            AND c.name = ?
        ORDER BY c.tcgcollector_card_id
        LIMIT 1
        """,
        (
            criteria["language"],
            criteria["set_code"],
            criteria["card_number"],
            criteria["name"],
        ),
    ).fetchone()
    if not row:
        raise SystemExit(f"Card not found for pricing seed: {criteria}")
    return row[0]


def clear_existing_seed_rows(conn: sqlite3.Connection) -> None:
    conn.execute(
        "DELETE FROM raw_price_records WHERE notes LIKE ?",
        (f"{SEED_NOTE_PREFIX}:%",),
    )
    conn.execute(
        "DELETE FROM graded_price_records WHERE notes LIKE ?",
        (f"{SEED_NOTE_PREFIX}:%",),
    )


def seed_raw_prices(conn: sqlite3.Connection) -> None:
    for record in RAW_PRICE_RECORDS:
        conn.execute(
            """
            INSERT INTO raw_price_records (
                card_id,
                source_id,
                checked_at,
                listing_type,
                price_cents,
                shipping_cents,
                currency,
                condition,
                listing_url,
                seller_name,
                notes
            )
            VALUES (?, ?, ?, ?, ?, 0, 'USD', ?, ?, ?, ?)
            """,
            (
                find_card(conn, record["card"]),
                source_id(conn, record["source"]),
                record["checked_at"],
                record["listing_type"],
                record["price_cents"],
                record["condition"],
                record["listing_url"],
                record["source"],
                record["notes"],
            ),
        )


def seed_graded_prices(conn: sqlite3.Connection) -> None:
    for record in GRADED_PRICE_RECORDS:
        conn.execute(
            """
            INSERT INTO graded_price_records (
                card_id,
                source_id,
                checked_at,
                grading_company,
                grade,
                listing_type,
                price_cents,
                shipping_cents,
                currency,
                listing_url,
                seller_name,
                notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 0, 'USD', ?, ?, ?)
            """,
            (
                find_card(conn, record["card"]),
                source_id(conn, record["source"]),
                record["checked_at"],
                record["grading_company"],
                record["grade"],
                record["listing_type"],
                record["price_cents"],
                record["listing_url"],
                record["seller_name"],
                record["notes"],
            ),
        )


def main() -> None:
    if not DB_PATH.exists():
        raise SystemExit(f"Database not found: {DB_PATH}. Run scripts/init_db.py first.")

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        clear_existing_seed_rows(conn)
        seed_raw_prices(conn)
        seed_graded_prices(conn)

    print(
        f"Seeded {len(RAW_PRICE_RECORDS)} raw price records and "
        f"{len(GRADED_PRICE_RECORDS)} graded price records into {DB_PATH}"
    )


if __name__ == "__main__":
    main()
