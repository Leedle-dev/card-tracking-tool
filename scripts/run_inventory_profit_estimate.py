from pathlib import Path
import argparse
import csv
import math
import sqlite3
import statistics


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "card_tracker.sqlite"
DEFAULT_OUTPUT_DIR = ROOT / "reports" / "inventory"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Estimate inventory proceeds using latest marketplace p25 price snapshots."
    )
    # Argument examples:
    #   --set-code CBB5C
    #   --set-code CBB5C --shipping-cents 100 --marketplace-fee-rate 0.1325
    #   --output reports/inventory/cbb5c_inventory_profit_estimate.tsv
    parser.add_argument("--set-code", default="", help="Optional set code filter, such as CBB5C.")
    parser.add_argument(
        "--db-path",
        type=Path,
        default=DB_PATH,
        help="Path to the local SQLite database.",
    )
    parser.add_argument(
        "--pricing-source",
        choices=["marketplace", "variations", "combined"],
        default="marketplace",
        help="Pricing data to use: single marketplace listings, item-group variations, or both.",
    )
    parser.add_argument(
        "--recalculate-from-raw",
        action="store_true",
        help="Recalculate snapshot stats from raw matched listing rows instead of using snapshot tables.",
    )
    parser.add_argument("--shipping-cents", type=int, default=100, help="Estimated shipping cost per card.")
    parser.add_argument(
        "--marketplace-fee-rate",
        type=float,
        default=0.1325,
        help="Marketplace fee rate applied after estimated shipping.",
    )
    parser.add_argument(
        "--minimum-cents",
        type=int,
        default=99,
        help="Minimum no-shipping listing price per card.",
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


def percentile(values: list[int], percent: float) -> float | None:
    if not values:
        return None
    sorted_values = sorted(values)
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    rank = (len(sorted_values) - 1) * percent
    low = int(rank)
    high = min(low + 1, len(sorted_values) - 1)
    fraction = rank - low
    return sorted_values[low] + (sorted_values[high] - sorted_values[low]) * fraction


def trimmed_mean(values: list[int], trim_rate: float = 0.1) -> float | None:
    if not values:
        return None
    sorted_values = sorted(values)
    trim_count = int(len(sorted_values) * trim_rate)
    if trim_count and len(sorted_values) > trim_count * 2:
        sorted_values = sorted_values[trim_count:-trim_count]
    return float(statistics.mean(sorted_values))


def stats_for_prices(values: list[int]) -> dict[str, float | int | None]:
    p25 = percentile(values, 0.25)
    p75 = percentile(values, 0.75)
    return {
        "listing_count": len(values),
        "p25_total_cents": p25,
        "median_total_cents": float(statistics.median(values)) if values else None,
        "min_total_cents": min(values) if values else None,
        "max_total_cents": max(values) if values else None,
        "mean_total_cents": float(statistics.mean(values)) if values else None,
        "stddev_total_cents": float(statistics.stdev(values)) if len(values) > 1 else 0.0 if values else None,
        "p10_total_cents": percentile(values, 0.10),
        "p75_total_cents": p75,
        "p90_total_cents": percentile(values, 0.90),
        "iqr_total_cents": (p75 - p25) if p25 is not None and p75 is not None else None,
        "trimmed_mean_total_cents": trimmed_mean(values),
    }


def add_shipping(value: float | int | None, shipping_cents: int) -> float | int | None:
    return None if value is None else value + shipping_cents


def fetch_inventory_rows(set_code: str, db_path: Path) -> list[sqlite3.Row]:
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
                AND LOWER(COALESCE(condition, '')) != 'graded'
            GROUP BY card_id
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
            c.holo_pattern
        FROM inventory i
        JOIN cards c ON c.id = i.card_id
        JOIN set_catalog sc ON sc.id = c.set_catalog_id
        WHERE 1 = 1
            {set_filter}
        ORDER BY sc.language, sc.set_name, c.source_sequence, c.card_number, c.id
    """

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(query, params).fetchall()


def fetch_snapshot_price_map(args: argparse.Namespace) -> dict[int, dict[str, object]]:
    with sqlite3.connect(args.db_path) as conn:
        conn.row_factory = sqlite3.Row
        normal_rows = []
        variation_rows = []
        if args.pricing_source in {"marketplace", "combined"}:
            normal_rows = conn.execute(
                """
                SELECT mps.*
                FROM marketplace_price_snapshots mps
                JOIN (
                    SELECT card_id, MAX(id) AS latest_snapshot_id
                    FROM marketplace_price_snapshots
                    GROUP BY card_id
                ) latest ON latest.latest_snapshot_id = mps.id
                """
            ).fetchall()
        if args.pricing_source in {"variations", "combined"}:
            variation_rows = conn.execute(
                """
                SELECT mvps.*
                FROM marketplace_variation_price_snapshots mvps
                JOIN (
                    SELECT card_id, MAX(id) AS latest_snapshot_id
                    FROM marketplace_variation_price_snapshots
                    GROUP BY card_id
                ) latest ON latest.latest_snapshot_id = mvps.id
                """
            ).fetchall()

    price_map: dict[int, dict[str, object]] = {}
    for row in normal_rows:
        price_map[int(row["card_id"])] = {
            "pricing_source_used": "marketplace",
            "listing_count": row["listing_count"],
            "marketplace_listing_count": row["listing_count"],
            "variation_listing_count": 0,
            "p25_total_cents": row["p25_total_cents"],
            "median_total_cents": row["median_total_cents"],
            "min_total_cents": row["min_total_cents"],
            "max_total_cents": row["max_total_cents"],
            "mean_total_cents": row["mean_total_cents"],
            "stddev_total_cents": row["stddev_total_cents"],
            "snapshot_created_at": row["created_at"],
        }

    for row in variation_rows:
        card_id = int(row["card_id"])
        variation_stats = {
            "pricing_source_used": "variations",
            "listing_count": row["variation_listing_count"],
            "marketplace_listing_count": 0,
            "variation_listing_count": row["variation_listing_count"],
            "p25_total_cents": add_shipping(row["p25_price_cents"], args.shipping_cents),
            "median_total_cents": add_shipping(row["median_price_cents"], args.shipping_cents),
            "min_total_cents": add_shipping(row["min_price_cents"], args.shipping_cents),
            "max_total_cents": add_shipping(row["max_price_cents"], args.shipping_cents),
            "mean_total_cents": add_shipping(row["mean_price_cents"], args.shipping_cents),
            "stddev_total_cents": row["stddev_price_cents"],
            "snapshot_created_at": row["created_at"],
        }
        if args.pricing_source == "variations" or card_id not in price_map:
            price_map[card_id] = variation_stats
        elif args.pricing_source == "combined":
            existing = price_map[card_id]
            existing["pricing_source_used"] = "combined_snapshots_approximate"
            existing["listing_count"] = int(existing["listing_count"] or 0) + int(row["variation_listing_count"] or 0)
            existing["variation_listing_count"] = row["variation_listing_count"]
            # This is an approximation because percentile snapshots cannot be perfectly merged.
            for key in ["p25_total_cents", "median_total_cents", "min_total_cents", "max_total_cents", "mean_total_cents"]:
                values = [value for value in [existing.get(key), variation_stats.get(key)] if value is not None]
                existing[key] = min(values) if key == "min_total_cents" and values else max(values) if key == "max_total_cents" and values else statistics.mean(values) if values else None
            existing["snapshot_created_at"] = max(str(existing["snapshot_created_at"] or ""), str(row["created_at"] or ""))
    return price_map


def fetch_raw_price_map(args: argparse.Namespace) -> dict[int, dict[str, object]]:
    observations: dict[int, list[tuple[str, int]]] = {}
    with sqlite3.connect(args.db_path) as conn:
        conn.row_factory = sqlite3.Row
        if args.pricing_source in {"marketplace", "combined"}:
            for row in conn.execute(
                """
                WITH latest_snapshots AS (
                    SELECT mps.card_id, mps.fetch_run_id
                    FROM marketplace_price_snapshots mps
                    JOIN (
                        SELECT card_id, MAX(id) AS latest_snapshot_id
                        FROM marketplace_price_snapshots
                        GROUP BY card_id
                    ) latest ON latest.latest_snapshot_id = mps.id
                )
                SELECT DISTINCT mlm.card_id, ml.total_price_cents
                FROM marketplace_listing_matches mlm
                JOIN marketplace_listings ml ON ml.id = mlm.listing_id
                JOIN latest_snapshots ls ON ls.card_id = mlm.card_id
                    AND ls.fetch_run_id = ml.fetch_run_id
                WHERE mlm.match_status = 'accepted'
                    AND ml.total_price_cents IS NOT NULL
                """
            ):
                observations.setdefault(int(row["card_id"]), []).append(("marketplace", int(row["total_price_cents"])))

        if args.pricing_source in {"variations", "combined"}:
            for row in conn.execute(
                """
                WITH latest_snapshots AS (
                    SELECT mvps.card_id, mvps.fetch_run_id
                    FROM marketplace_variation_price_snapshots mvps
                    JOIN (
                        SELECT card_id, MAX(id) AS latest_snapshot_id
                        FROM marketplace_variation_price_snapshots
                        GROUP BY card_id
                    ) latest ON latest.latest_snapshot_id = mvps.id
                )
                SELECT DISTINCT migvm.card_id, migv.price_cents
                FROM marketplace_item_group_variation_matches migvm
                JOIN marketplace_item_group_variations migv ON migv.id = migvm.item_group_variation_id
                JOIN latest_snapshots ls ON ls.card_id = migvm.card_id
                    AND ls.fetch_run_id = migvm.fetch_run_id
                WHERE migv.price_cents IS NOT NULL
                    AND UPPER(COALESCE(migv.estimated_availability_status, '')) != 'OUT_OF_STOCK'
                    AND COALESCE(migv.estimated_available_quantity, 1) > 0
                """
            ):
                observations.setdefault(int(row["card_id"]), []).append(
                    ("variations", int(row["price_cents"]) + args.shipping_cents)
                )

    price_map: dict[int, dict[str, object]] = {}
    for card_id, values in observations.items():
        prices = [price for _, price in values]
        stats = stats_for_prices(prices)
        marketplace_count = sum(1 for source, _ in values if source == "marketplace")
        variation_count = sum(1 for source, _ in values if source == "variations")
        stats.update(
            {
                "pricing_source_used": args.pricing_source + "_raw",
                "marketplace_listing_count": marketplace_count,
                "variation_listing_count": variation_count,
                "snapshot_created_at": "recalculated_from_raw",
            }
        )
        price_map[card_id] = stats
    return price_map


def attach_price_data(rows: list[sqlite3.Row], price_map: dict[int, dict[str, object]]) -> list[dict[str, object]]:
    combined_rows = []
    for row in rows:
        item = dict(row)
        item.update(
            {
                "pricing_source_used": "",
                "listing_count": None,
                "marketplace_listing_count": 0,
                "variation_listing_count": 0,
                "p25_total_cents": None,
                "median_total_cents": None,
                "min_total_cents": None,
                "max_total_cents": None,
                "mean_total_cents": None,
                "stddev_total_cents": None,
                "snapshot_created_at": None,
            }
        )
        item.update(price_map.get(int(row["card_id"]), {}))
        combined_rows.append(item)
    return combined_rows


def fetch_rows(args: argparse.Namespace) -> list[dict[str, object]]:
    if args.pricing_source == "combined" and not args.recalculate_from_raw:
        print("Combined snapshot mode is approximate. Use --recalculate-from-raw for true combined percentiles.")
    inventory_rows = fetch_inventory_rows(args.set_code, args.db_path)
    price_map = fetch_raw_price_map(args) if args.recalculate_from_raw else fetch_snapshot_price_map(args)
    return attach_price_data(inventory_rows, price_map)


def write_report(rows: list[dict[str, object]], args: argparse.Namespace, output_path: Path) -> tuple[int, int, int]:
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
        "pricing_source_used",
        "listing_count",
        "marketplace_listing_count",
        "variation_listing_count",
        "p25_total_cents",
        "p25_total",
        "mean_total_cents",
        "mean_total",
        "median_total_cents",
        "median_total",
        "min_total_cents",
        "min_total",
        "max_total_cents",
        "max_total",
        "stddev_total_cents",
        "stddev_total",
        "estimated_shipping_cents",
        "estimated_shipping",
        "LISTING_PRICE_CENTS",
        "LISTING_PRICE",
        "unit_gross_after_shipping_cents",
        "unit_gross_after_shipping",
        "unit_marketplace_fee_cents",
        "unit_marketplace_fee",
        "unit_net_after_fee_cents",
        "unit_net_after_fee",
        "total_gross_after_shipping_cents",
        "total_gross_after_shipping",
        "total_marketplace_fee_cents",
        "total_marketplace_fee",
        "total_net_after_fee_cents",
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
                    "pricing_source_used": row["pricing_source_used"],
                    "listing_count": row["listing_count"],
                    "marketplace_listing_count": row["marketplace_listing_count"],
                    "variation_listing_count": row["variation_listing_count"],
                    "p25_total_cents": row["p25_total_cents"],
                    "p25_total": cents_to_dollars(row["p25_total_cents"]),
                    "mean_total_cents": row["mean_total_cents"],
                    "mean_total": cents_to_dollars(row["mean_total_cents"]),
                    "median_total_cents": row["median_total_cents"],
                    "median_total": cents_to_dollars(row["median_total_cents"]),
                    "min_total_cents": row["min_total_cents"],
                    "min_total": cents_to_dollars(row["min_total_cents"]),
                    "max_total_cents": row["max_total_cents"],
                    "max_total": cents_to_dollars(row["max_total_cents"]),
                    "stddev_total_cents": row["stddev_total_cents"],
                    "stddev_total": cents_to_dollars(row["stddev_total_cents"]),
                    "estimated_shipping_cents": args.shipping_cents,
                    "estimated_shipping": cents_to_dollars(args.shipping_cents),
                    "LISTING_PRICE_CENTS": unit_gross_cents,
                    "LISTING_PRICE": cents_to_dollars(unit_gross_cents),
                    "unit_gross_after_shipping_cents": unit_gross_cents,
                    "unit_gross_after_shipping": cents_to_dollars(unit_gross_cents),
                    "unit_marketplace_fee_cents": unit_fee_cents,
                    "unit_marketplace_fee": cents_to_dollars(unit_fee_cents),
                    "unit_net_after_fee_cents": unit_net_cents,
                    "unit_net_after_fee": cents_to_dollars(unit_net_cents),
                    "total_gross_after_shipping_cents": total_row_gross_cents,
                    "total_gross_after_shipping": cents_to_dollars(total_row_gross_cents),
                    "total_marketplace_fee_cents": total_row_fee_cents,
                    "total_marketplace_fee": cents_to_dollars(total_row_fee_cents),
                    "total_net_after_fee_cents": total_row_net_cents,
                    "total_net_after_fee": cents_to_dollars(total_row_net_cents),
                    "snapshot_created_at": row["snapshot_created_at"],
                }
            )

    return total_quantity, total_gross_cents, total_net_cents


def main() -> None:
    args = parse_args()
    rows = fetch_rows(args)
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
