from __future__ import annotations

from pathlib import Path
import argparse
import sqlite3
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


DB_PATH = ROOT / "data" / "card_tracker.sqlite"
ELIGIBLE_RARITY_PREFIXES = ("Common", "Uncommon", "Rare")
DEFAULT_NOTES = "synthetic_parallel_variant: source set has physical parallel prints not tracked by TCGcollector"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Add synthetic parallel holo variant rows for imported sets.")
    # Argument examples:
    #   python scripts/add_parallel_holo_variants.py --set-code CS5aC --set-name "Brave Stars (Charm)" --holo-pattern "Energy Holo"
    #   python scripts/add_parallel_holo_variants.py --set-code CS5aC --dry-run
    parser.add_argument("--set-code", required=True, help="Set code, such as CS5aC.")
    parser.add_argument("--set-name", default="", help="Optional set name disambiguator.")
    parser.add_argument("--holo-pattern", default="Energy Holo", help="Parallel holo pattern to add.")
    parser.add_argument("--db-path", type=Path, default=DB_PATH, help="Path to SQLite database.")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be created without writing.")
    return parser.parse_args()


def resolve_path(path: Path) -> Path:
    return path if path.is_absolute() else ROOT / path


def is_eligible_rarity(rarity: str | None) -> bool:
    if not rarity:
        return False
    return any(rarity.startswith(prefix) for prefix in ELIGIBLE_RARITY_PREFIXES)


def fetch_base_cards(conn: sqlite3.Connection, set_code: str, set_name: str) -> list[sqlite3.Row]:
    params: list[str] = [set_code]
    set_name_filter = ""
    if set_name:
        set_name_filter = "AND lower(sc.set_name) = lower(?)"
        params.append(set_name)

    rows = conn.execute(
        f"""
        SELECT
            c.*,
            sc.set_name,
            sc.set_code
        FROM cards c
        JOIN set_catalog sc ON sc.id = c.set_catalog_id
        WHERE lower(sc.set_code) = lower(?)
            {set_name_filter}
            AND c.tcgcollector_card_id IS NOT NULL
        ORDER BY c.source_sequence, c.card_number, c.name
        """,
        params,
    ).fetchall()
    return [row for row in rows if is_eligible_rarity(row["rarity"])]


def variant_exists(conn: sqlite3.Connection, base: sqlite3.Row, holo_pattern: str) -> bool:
    return (
        conn.execute(
            """
            SELECT 1
            FROM cards
            WHERE set_catalog_id = ?
                AND name = ?
                AND COALESCE(card_number, '') = COALESCE(?, '')
                AND COALESCE(holo_pattern, '') = ?
            LIMIT 1
            """,
            (base["set_catalog_id"], base["name"], base["card_number"], holo_pattern),
        ).fetchone()
        is not None
    )


def create_variant(conn: sqlite3.Connection, base: sqlite3.Row, holo_pattern: str) -> int:
    notes = "; ".join(part for part in [DEFAULT_NOTES, f"base_card_id={base['id']}"] if part)
    cursor = conn.execute(
        """
        INSERT INTO cards (
            set_catalog_id,
            pokedex_id,
            name,
            game,
            card_number,
            pokemon_name,
            rarity,
            holo_pattern,
            source_sequence,
            tcgcollector_card_id,
            card_detail_url,
            is_regional_exclusive,
            notes,
            primary_image_path
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?)
        """,
        (
            base["set_catalog_id"],
            base["pokedex_id"],
            base["name"],
            base["game"],
            base["card_number"],
            base["pokemon_name"],
            base["rarity"],
            holo_pattern,
            (base["source_sequence"] or 0) + 100000,
            base["card_detail_url"],
            base["is_regional_exclusive"],
            notes,
            base["primary_image_path"],
        ),
    )
    card_id = int(cursor.lastrowid)
    conn.execute(
        """
        INSERT INTO card_inventory (card_id, sale_status, notes)
        VALUES (?, 'reference', ?)
        """,
        (card_id, notes),
    )
    return card_id


def main() -> None:
    args = parse_args()
    conn = sqlite3.connect(resolve_path(args.db_path))
    conn.row_factory = sqlite3.Row
    try:
        base_cards = fetch_base_cards(conn, args.set_code, args.set_name)
        created = []
        skipped = []
        for base in base_cards:
            if variant_exists(conn, base, args.holo_pattern):
                skipped.append(base)
                continue
            if not args.dry_run:
                card_id = create_variant(conn, base, args.holo_pattern)
                created.append((base, card_id))
            else:
                created.append((base, None))
        if args.dry_run:
            conn.rollback()
        else:
            conn.commit()
    finally:
        conn.close()

    action = "Would create" if args.dry_run else "Created"
    print(f"{action} {len(created)} {args.holo_pattern} variants for {args.set_code}.")
    print(f"Skipped {len(skipped)} existing variants.")
    for base, card_id in created[:20]:
        suffix = f" -> card_id {card_id}" if card_id else ""
        print(f"{base['card_number']} {base['name']} ({base['rarity']}){suffix}")
    if len(created) > 20:
        print(f"... {len(created) - 20} more")


if __name__ == "__main__":
    main()
