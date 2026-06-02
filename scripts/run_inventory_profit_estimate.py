from pathlib import Path
import argparse
import csv
import math
import sqlite3


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "card_tracker.sqlite"
DEFAULT_OUTPUT_DIR = ROOT / "reports" / "inventory"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Estimate inventory proceeds using latest marketplace p25 price snapshots."
    )
    # Argument examples:
    #   --set-code CBB5C
    #   --set-code CBB5C --shipping-cents 125 --marketplace-fee-rate 0.1325
    #   --output reports/inventory/cbb5c_inventory_profit_estimate.tsv
    parser.add_argument("--set-code", default="", help="Optional set code filter, such as CBB5C.")
    parser.add_argument("--shipping-cents", type=int, default=125, help="Estimated shipping cost per card.")
    parser.add_argument(
        "--marketplace-fee-rate",
        type=float,
        default=0.1325,
        help="Marketplace fee rate applied after estimated shipping.",
    )
    parser.add_argument(
        "--minimum-cents",
        type=int,
        default=75,
        help="Minimum per-card estimated gross profit/listing basis after shipping.",
    )
    parser.add_argument(
        "--floor-increment-cents",
        type=int,
        default=25,
        help="Floor per-card estimate to this cent increment after shipping.",
    )
    parser.add_argument("--output", default="", help="Optional TSV output path.")
    return parser.parse_args()


def cents_to_dollars(cents: float | int | None) -> str:
    if cents is None:
        return ""
    return f"${cents / 100:,.2f}"


def estimate_unit_gross_cents(
    p25_total_cents: float,
    shipping_cents: int,
    floor_increment_cents: int,
    minimum_cents: int,
) -> int:
    after_shipping = p25_total_cents - shipping_cents
    floored = math.floor(after_shipping / floor_increment_cents) * floor_increment_cents
    return max(minimum_cents, floored)


def fetch_rows(set_code: str) -> list[sqlite3.Row]:
    set_filter = ""
    params: list[str] = []
    if set_code:
        set_filter = "AND LOWER(sc.set_code) = LOWER(?)"
        params.append(set_code)

    query = f"""
        WITH inventory AS (
            SELECT
                card_id,
                SUM(quantity) AS quantity
            FROM card_inventory
            WHERE sale_status != 'reference'
            GROUP BY card_id
        ),
        latest_snapshots AS (
            SELECT mps.*
            FROM marketplace_price_snapshots mps
            JOIN (
                SELECT card_id, MAX(id) AS latest_snapshot_id
                FROM marketplace_price_snapshots
                GROUP BY card_id
            ) latest ON latest.latest_snapshot_id = mps.id
        )
        SELECT
            i.card_id,
            i.quantity,
            sc.language,
            sc.set_code,
            sc.set_name,
            c.card_number,
            c.name AS card_name,
            c.pokemon_name,
            c.rarity,
            c.holo_pattern,
            ls.listing_count,
            ls.p25_total_cents,
            ls.median_total_cents,
            ls.min_total_cents,
            ls.max_total_cents,
            ls.created_at AS snapshot_created_at
        FROM inventory i
        JOIN cards c ON c.id = i.card_id
        JOIN set_catalog sc ON sc.id = c.set_catalog_id
        LEFT JOIN latest_snapshots ls ON ls.card_id = i.card_id
        WHERE 1 = 1
            {set_filter}
        ORDER BY sc.language, sc.set_name, c.source_sequence, c.card_number, c.id
    """

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(query, params).fetchall()


def write_report(rows: list[sqlite3.Row], args: argparse.Namespace, output_path: Path) -> tuple[int, int, int]:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    total_quantity = 0
    total_gross_cents = 0
    total_net_cents = 0

    fieldnames = [
        "card_id",
        "quantity",
        "language",
        "set_code",
        "set_name",
        "card_number",
        "card_name",
        "pokemon_name",
        "rarity",
        "holo_pattern",
        "listing_count",
        "p25_total",
        "median_total",
        "min_total",
        "max_total",
        "estimated_shipping",
        "unit_gross_after_shipping",
        "unit_marketplace_fee",
        "unit_net_after_fee",
        "total_gross_after_shipping",
        "total_marketplace_fee",
        "total_net_after_fee",
        "snapshot_created_at",
    ]

    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()

        for row in rows:
            quantity = int(row["quantity"])
            p25_total_cents = row["p25_total_cents"]

            if p25_total_cents is None:
                unit_gross_cents = 0
            else:
                unit_gross_cents = estimate_unit_gross_cents(
                    p25_total_cents=p25_total_cents,
                    shipping_cents=args.shipping_cents,
                    floor_increment_cents=args.floor_increment_cents,
                    minimum_cents=args.minimum_cents,
                )

            unit_fee_cents = round(unit_gross_cents * args.marketplace_fee_rate)
            unit_net_cents = unit_gross_cents - unit_fee_cents
            total_row_gross_cents = unit_gross_cents * quantity
            total_row_fee_cents = unit_fee_cents * quantity
            total_row_net_cents = unit_net_cents * quantity

            total_quantity += quantity
            total_gross_cents += total_row_gross_cents
            total_net_cents += total_row_net_cents

            writer.writerow(
                {
                    "card_id": row["card_id"],
                    "quantity": quantity,
                    "language": row["language"],
                    "set_code": row["set_code"],
                    "set_name": row["set_name"],
                    "card_number": row["card_number"],
                    "card_name": row["card_name"],
                    "pokemon_name": row["pokemon_name"],
                    "rarity": row["rarity"],
                    "holo_pattern": row["holo_pattern"],
                    "listing_count": row["listing_count"],
                    "p25_total": cents_to_dollars(row["p25_total_cents"]),
                    "median_total": cents_to_dollars(row["median_total_cents"]),
                    "min_total": cents_to_dollars(row["min_total_cents"]),
                    "max_total": cents_to_dollars(row["max_total_cents"]),
                    "estimated_shipping": cents_to_dollars(args.shipping_cents),
                    "unit_gross_after_shipping": cents_to_dollars(unit_gross_cents),
                    "unit_marketplace_fee": cents_to_dollars(unit_fee_cents),
                    "unit_net_after_fee": cents_to_dollars(unit_net_cents),
                    "total_gross_after_shipping": cents_to_dollars(total_row_gross_cents),
                    "total_marketplace_fee": cents_to_dollars(total_row_fee_cents),
                    "total_net_after_fee": cents_to_dollars(total_row_net_cents),
                    "snapshot_created_at": row["snapshot_created_at"],
                }
            )

    return total_quantity, total_gross_cents, total_net_cents


def main() -> None:
    args = parse_args()
    rows = fetch_rows(args.set_code)
    if not rows:
        raise SystemExit("No non-reference inventory rows found for the requested filters.")

    if args.output:
        output_path = Path(args.output)
        if not output_path.is_absolute():
            output_path = ROOT / output_path
    else:
        name = f"{args.set_code.lower()}_" if args.set_code else ""
        output_path = DEFAULT_OUTPUT_DIR / f"{name}inventory_profit_estimate.tsv"

    total_quantity, total_gross_cents, total_net_cents = write_report(rows, args, output_path)

    print(f"Cards with inventory: {len(rows)}")
    print(f"Total quantity: {total_quantity}")
    print(f"Total gross after shipping: {cents_to_dollars(total_gross_cents)}")
    print(f"Total net after {args.marketplace_fee_rate:.4f} marketplace fee: {cents_to_dollars(total_net_cents)}")
    print(output_path)


if __name__ == "__main__":
    main()
