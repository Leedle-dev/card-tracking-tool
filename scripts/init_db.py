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
    ("PriceCharting", "https://www.pricecharting.com", "Price guide, population, and historic sale aggregation source."),
    ("Manual Comp", None, "Manually entered comparable sale or listing."),
]

GRADING_COMPANIES = [
    (
        "Professional Sports Authenticator",
        "PSA",
        "https://www.psacard.com",
        "Major grading company. PSA 10 is generally treated as gem mint.",
    ),
    (
        "Beckett Grading Services",
        "BGS",
        "https://www.beckett.com/grading",
        "Beckett grading company. BGS gem threshold is generally 9.5+.",
    ),
    (
        "CGC Cards",
        "CGC",
        "https://www.cgccards.com",
        "CGC grading company with Gem Mint 10 and Pristine 10 distinctions.",
    ),
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
    (
        "BGS Bulk Estimate",
        "BGS",
        "Bulk",
        1500,
        125,
        200,
        0.1325,
        "Beckett bulk grading estimate using per-card multi-submission shipping allocations.",
    ),
]


LANGUAGE_BY_REGION = {
    "international": "English",
    "japanese": "Japanese",
    "s-chinese": "Simplified Chinese",
}

ACTIVE_CARD_COLUMNS = [
    "id",
    "set_catalog_id",
    "pokedex_id",
    "name",
    "game",
    "card_number",
    "pokemon_name",
    "rarity",
    "holo_pattern",
    "source_sequence",
    "tcgcollector_card_id",
    "card_detail_url",
    "is_regional_exclusive",
    "notes",
    "primary_image_path",
    "created_at",
    "updated_at",
]

INVENTORY_COLUMNS_MOVED_FROM_CARDS = [
    "condition",
    "quantity",
    "cost_basis_cents",
    "acquisition_date",
    "sale_status",
]


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


def create_card_inventory_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS card_inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            card_id INTEGER NOT NULL UNIQUE,
            condition TEXT,
            quantity INTEGER NOT NULL DEFAULT 1 CHECK (quantity >= 0),
            cost_basis_cents INTEGER NOT NULL DEFAULT 0 CHECK (cost_basis_cents >= 0),
            acquisition_date TEXT,
            sale_status TEXT NOT NULL DEFAULT 'inventory',
            notes TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (card_id) REFERENCES cards(id) ON DELETE CASCADE
        )
        """
    )


def rebuild_cards_for_current_shape(conn: sqlite3.Connection) -> None:
    card_columns = column_names(conn, "cards")
    legacy_columns = {
        "pokemon_index",
        "variant_code",
        "is_chinese_exclusive",
        "set_name",
        "set_code",
        "language",
        "region",
        "release_year",
        *INVENTORY_COLUMNS_MOVED_FROM_CARDS,
    }
    needs_rebuild = bool(legacy_columns & card_columns) or (
        card_columns and "is_regional_exclusive" not in card_columns
    )
    if not needs_rebuild:
        return

    create_card_inventory_table(conn)
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        conn.execute("DROP TABLE IF EXISTS cards_new")
        conn.execute(
            """
            CREATE TABLE cards_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                set_catalog_id INTEGER,
                pokedex_id INTEGER,
                name TEXT NOT NULL,
                game TEXT NOT NULL DEFAULT 'Pokemon',
                card_number TEXT,
                pokemon_name TEXT,
                rarity TEXT,
                holo_pattern TEXT,
                source_sequence INTEGER,
                tcgcollector_card_id INTEGER,
                card_detail_url TEXT,
                is_regional_exclusive INTEGER NOT NULL DEFAULT 0 CHECK (is_regional_exclusive IN (0, 1)),
                notes TEXT,
                primary_image_path TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (set_catalog_id) REFERENCES set_catalog(id),
                FOREIGN KEY (pokedex_id) REFERENCES pokedex(id)
            )
            """
        )
        source_exclusive_column = (
            "is_regional_exclusive"
            if "is_regional_exclusive" in card_columns
            else "is_chinese_exclusive"
            if "is_chinese_exclusive" in card_columns
            else "0"
        )
        select_columns = [
            source_exclusive_column if column == "is_regional_exclusive" else column
            for column in ACTIVE_CARD_COLUMNS
        ]
        columns = ", ".join(ACTIVE_CARD_COLUMNS)
        select_clause = ", ".join(select_columns)
        conn.execute(
            f"""
            INSERT INTO cards_new ({columns})
            SELECT {select_clause}
            FROM cards
            """
        )
        if set(INVENTORY_COLUMNS_MOVED_FROM_CARDS) & card_columns:
            conn.execute(
                """
                INSERT INTO card_inventory (
                    card_id,
                    condition,
                    quantity,
                    cost_basis_cents,
                    acquisition_date,
                    sale_status
                )
                SELECT
                    id,
                    condition,
                    quantity,
                    cost_basis_cents,
                    acquisition_date,
                    sale_status
                FROM cards
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM card_inventory
                    WHERE card_inventory.card_id = cards.id
                )
                """
            )
            conn.execute(
                """
                UPDATE card_inventory
                SET
                    condition = (
                        SELECT cards.condition
                        FROM cards
                        WHERE cards.id = card_inventory.card_id
                    ),
                    quantity = (
                        SELECT cards.quantity
                        FROM cards
                        WHERE cards.id = card_inventory.card_id
                    ),
                    cost_basis_cents = (
                        SELECT cards.cost_basis_cents
                        FROM cards
                        WHERE cards.id = card_inventory.card_id
                    ),
                    acquisition_date = (
                        SELECT cards.acquisition_date
                        FROM cards
                        WHERE cards.id = card_inventory.card_id
                    ),
                    sale_status = (
                        SELECT cards.sale_status
                        FROM cards
                        WHERE cards.id = card_inventory.card_id
                    )
                WHERE EXISTS (
                    SELECT 1
                    FROM cards
                    WHERE cards.id = card_inventory.card_id
                )
                """
            )
        conn.execute("DROP TABLE cards")
        conn.execute("ALTER TABLE cards_new RENAME TO cards")
    finally:
        conn.execute("PRAGMA foreign_keys = ON")


def pre_schema_migrations(conn: sqlite3.Connection) -> None:
    pokedex_columns = column_names(conn, "pokedex")
    if pokedex_columns and "variant_name" not in pokedex_columns:
        pokedex_count = conn.execute("SELECT COUNT(*) FROM pokedex").fetchone()[0]
        if pokedex_count == 0:
            conn.execute("DROP TABLE pokedex")
        else:
            conn.execute("ALTER TABLE pokedex ADD COLUMN variant_name TEXT")
            conn.execute("ALTER TABLE pokedex ADD COLUMN form_name TEXT")
            conn.execute("ALTER TABLE pokedex ADD COLUMN source_slug TEXT")
    elif pokedex_columns:
        unique_indexes = [
            row
            for row in conn.execute("PRAGMA index_list(pokedex)").fetchall()
            if row[2]
        ]
        if len(unique_indexes) > 1:
            pokedex_count = conn.execute("SELECT COUNT(*) FROM pokedex").fetchone()[0]
            if pokedex_count == 0:
                conn.execute("DROP TABLE pokedex")

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

    grading_profile_columns = column_names(conn, "grading_profiles")
    if grading_profile_columns and "grading_company_id" not in grading_profile_columns:
        conn.execute("ALTER TABLE grading_profiles ADD COLUMN grading_company_id INTEGER")

    backfill_set_catalog(conn)
    backfill_card_set_catalog_links(conn)
    rebuild_cards_for_current_shape(conn)


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
    card_columns = column_names(conn, "cards")
    if not {"set_code", "set_name", "language"} <= card_columns:
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


def backfill_card_inventory(conn: sqlite3.Connection) -> None:
    if not table_exists(conn, "cards") or not table_exists(conn, "card_inventory"):
        return

    conn.execute(
        """
        INSERT INTO card_inventory (card_id, sale_status)
        SELECT id, 'reference'
        FROM cards
        WHERE NOT EXISTS (
            SELECT 1
            FROM card_inventory
            WHERE card_inventory.card_id = cards.id
        )
        """
    )


def backfill_grading_profile_company_links(conn: sqlite3.Connection) -> None:
    if not table_exists(conn, "grading_profiles") or not table_exists(conn, "grading_companies"):
        return

    conn.execute(
        """
        UPDATE grading_profiles
        SET grading_company_id = (
            SELECT gc.id
            FROM grading_companies gc
            WHERE gc.abbreviation = grading_profiles.grading_company
            LIMIT 1
        )
        WHERE grading_company_id IS NULL
        """
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
        backfill_card_inventory(conn)
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
            INSERT INTO grading_companies (name, abbreviation, website_url, notes)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(abbreviation) DO UPDATE SET
                name = excluded.name,
                website_url = excluded.website_url,
                notes = excluded.notes
            """,
            GRADING_COMPANIES,
        )
        conn.executemany(
            """
            INSERT INTO grading_profiles (
                name,
                grading_company_id,
                grading_company,
                service_level,
                grading_fee_cents,
                inbound_shipping_cents,
                return_shipping_cents,
                marketplace_fee_rate,
                notes
            )
            VALUES (
                ?,
                (SELECT id FROM grading_companies WHERE abbreviation = ?),
                ?, ?, ?, ?, ?, ?, ?
            )
            ON CONFLICT(name) DO NOTHING
            """,
            [
                (
                    name,
                    grading_company,
                    grading_company,
                    service_level,
                    grading_fee_cents,
                    inbound_shipping_cents,
                    return_shipping_cents,
                    marketplace_fee_rate,
                    notes,
                )
                for (
                    name,
                    grading_company,
                    service_level,
                    grading_fee_cents,
                    inbound_shipping_cents,
                    return_shipping_cents,
                    marketplace_fee_rate,
                    notes,
                ) in GRADING_PROFILES
            ],
        )
        backfill_grading_profile_company_links(conn)

    print(f"Database initialized at {DB_PATH}")


if __name__ == "__main__":
    main()
