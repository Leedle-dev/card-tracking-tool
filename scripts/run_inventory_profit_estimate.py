from pathlib import Path
import argparse
import csv
import math
import sqlite3
import statistics
import sys

from openpyxl import Workbook
from openpyxl import load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from card_tracker.report_paths import timestamped_report_dir

DB_PATH = ROOT / "data" / "card_tracker.sqlite"

METRIC_COLUMN_FILL = "DDEBF7"
GOOD_PRICE_FILL = "D9EAD3"
REVIEW_FILLS = {
    "OK": GOOD_PRICE_FILL,
    "Yellow": "FFF2CC",
    "Orange": "FCE4D6",
    "Red": "F4CCCC",
    "No Data": "B85450",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Estimate inventory proceeds using latest marketplace p25 price snapshots."
    )
    # Argument examples:
    #   --set-code CBB5C
    #   --set-code CBB5C --shipping-cents 100 --marketplace-fee-rate 0.1325
    #   --report-label cbb5c_inventory
    #   --output reports/inventory_profit_estimate/YYYYMMDD_HHMMSS_label/inventory_profit_estimate.tsv
    parser.add_argument("--set-code", default="", help="Optional set code filter, such as CBB5C.")
    parser.add_argument("--card-id", type=int, help="Optional cards.id filter for one card.")
    parser.add_argument(
        "--inventory-where",
        default="",
        help=(
            "Optional SQL WHERE clause for inventory rows. "
            "Available aliases: c=cards, ci=card_inventory, sc=set_catalog."
        ),
    )
    parser.add_argument(
        "--include-reference",
        action="store_true",
        help="Include card_inventory rows with sale_status='reference'. Useful for pricing reference cards.",
    )
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
    parser.add_argument(
        "--use-snapshot-tables",
        action="store_true",
        help=(
            "Use precomputed snapshot tables instead of raw rows. Raw recalculation is the default "
            "so graded listings and variation-parent listings can be excluded."
        ),
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
    parser.add_argument(
        "--report-label",
        default="",
        help="Optional label for the generated timestamped report folder when --output is omitted.",
    )
    parser.add_argument(
        "--seller-location-split",
        action="store_true",
        help="Write separate TSVs for US sellers, international sellers, and aggregate pricing.",
    )
    parser.add_argument(
        "--listing-card-condition",
        default="",
        help='Only use listing rows with this normalized card condition, such as "NM/Mint".',
    )
    parser.add_argument(
        "--match-inventory-condition",
        action="store_true",
        help="Only use listing rows whose normalized card_condition matches card_inventory.condition.",
    )
    parser.add_argument(
        "--order-workbook",
        type=Path,
        help="Optional binder intake workbook whose row order should drive report row order.",
    )
    parser.add_argument(
        "--order-sheet",
        default="Binder Intake",
        help="Sheet name to read when --order-workbook is supplied.",
    )
    return parser.parse_args()


def cents_to_dollars(cents: float | int | None) -> str:
    if cents is None:
        return ""
    return f"${cents / 100:,.2f}"


def round_or_none(value: float | int | None, digits: int = 2) -> float | int | None:
    return None if value is None else round(float(value), digits)


def ratio(numerator: float | int | None, denominator: float | int | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return abs(float(numerator) / float(denominator))


def review_flag_and_reasons(row: dict[str, object], listing_price_cents: int, shipping_cents: int) -> tuple[str, str]:
    reasons = []
    severity = 0
    listing_count = int(row.get("listing_count") or 0)
    median = row.get("median_total_cents")
    mean = row.get("mean_total_cents")
    stddev = row.get("stddev_total_cents")
    listed_total = listing_price_cents + shipping_cents

    if listing_count < 3:
        severity = max(severity, 3)
        reasons.append("fewer than 3 accepted listings")

    stddev_ratio = ratio(stddev, median)
    if stddev_ratio is not None:
        if stddev_ratio >= 0.75:
            severity = max(severity, 3)
            reasons.append(f"stddev is {stddev_ratio:.0%} of median")
        elif stddev_ratio >= 0.45:
            severity = max(severity, 2)
            reasons.append(f"stddev is {stddev_ratio:.0%} of median")
        elif stddev_ratio >= 0.25:
            severity = max(severity, 1)
            reasons.append(f"stddev is {stddev_ratio:.0%} of median")

    mean_median_gap = ratio(float(mean) - float(median), median) if mean is not None and median is not None else None
    if mean_median_gap is not None:
        if mean_median_gap >= 0.50:
            severity = max(severity, 3)
            reasons.append(f"mean/median spread is {mean_median_gap:.0%}")
        elif mean_median_gap >= 0.30:
            severity = max(severity, 2)
            reasons.append(f"mean/median spread is {mean_median_gap:.0%}")
        elif mean_median_gap >= 0.15:
            severity = max(severity, 1)
            reasons.append(f"mean/median spread is {mean_median_gap:.0%}")

    listing_median_gap = ratio(float(listed_total) - float(median), median) if median is not None else None
    if listing_median_gap is not None:
        if listing_median_gap >= 0.60:
            severity = max(severity, 3)
            reasons.append(f"listing total vs median gap is {listing_median_gap:.0%}")
        elif listing_median_gap >= 0.35:
            severity = max(severity, 2)
            reasons.append(f"listing total vs median gap is {listing_median_gap:.0%}")
        elif listing_median_gap >= 0.20:
            severity = max(severity, 1)
            reasons.append(f"listing total vs median gap is {listing_median_gap:.0%}")

    if severity == 3:
        return "Red", "; ".join(reasons)
    if severity == 2:
        return "Orange", "; ".join(reasons)
    if severity == 1:
        return "Yellow", "; ".join(reasons)
    return "OK", ""


def estimate_unit_gross_cents(
    p25_total_cents: float,
    shipping_cents: int,
    floor_increment_cents: int,
    minimum_cents: int,
) -> int:
    after_shipping = p25_total_cents - shipping_cents
    floored = math.floor(after_shipping / floor_increment_cents) * floor_increment_cents
    return apply_charm_price(max(minimum_cents, floored), minimum_cents)


def apply_charm_price(price_cents: int, minimum_cents: int = 99) -> int:
    if price_cents <= minimum_cents:
        return minimum_cents
    if price_cents % 25 == 0:
        return max(minimum_cents, price_cents - 1)
    return price_cents


def nearest_increment_cents(value: float, increment_cents: int) -> int:
    return int(math.floor((value / increment_cents) + 0.5) * increment_cents)


def estimate_blended_listing_price_cents(
    p25_total_cents: float | int | None,
    median_total_cents: float | int | None,
    shipping_cents: int,
    increment_cents: int,
    minimum_cents: int,
) -> int:
    values = [float(value) for value in [p25_total_cents, median_total_cents] if value is not None]
    if not values:
        return 0
    blended_total = statistics.mean(values)
    rounded = nearest_increment_cents(blended_total - shipping_cents, increment_cents)
    return apply_charm_price(max(minimum_cents, rounded), minimum_cents)


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


def remove_stddev_outliers(values: list[int], stddev_multiplier: float = 3.0) -> tuple[list[int], int]:
    if len(values) < 3:
        return values, 0
    mean_value = statistics.mean(values)
    stddev_value = statistics.stdev(values)
    if stddev_value == 0:
        return values, 0
    lower_bound = mean_value - (stddev_multiplier * stddev_value)
    upper_bound = mean_value + (stddev_multiplier * stddev_value)
    cleaned = [value for value in values if lower_bound <= value <= upper_bound]
    return cleaned, len(values) - len(cleaned)


def two_pass_stats_for_prices(values: list[int]) -> dict[str, float | int | None]:
    original_count = len(values)
    cleaned_values, outlier_count = remove_stddev_outliers(values)
    stats = stats_for_prices(cleaned_values)
    stats["original_listing_count"] = original_count
    stats["outlier_listing_count"] = outlier_count
    return stats


def add_shipping(value: float | int | None, shipping_cents: int) -> float | int | None:
    return None if value is None else value + shipping_cents


def fetch_inventory_rows(
    set_code: str,
    db_path: Path,
    card_id: int | None = None,
    include_reference: bool = False,
    inventory_where: str = "",
) -> list[sqlite3.Row]:
    set_filter = ""
    card_filter = ""
    sale_status_filter = "" if include_reference else "AND ci.sale_status != 'reference'"
    custom_inventory_filter = f"AND ({inventory_where})" if inventory_where else ""
    params: list[str | int] = []
    if set_code:
        set_filter = "AND LOWER(sc.set_code) = LOWER(?)"
        params.append(set_code)
    if card_id is not None:
        card_filter = "AND c.id = ?"
        params.append(card_id)

    query = f"""
        SELECT
            c.id AS card_id,
            SUM(ci.quantity) AS quantity,
            sc.language,
            sc.set_code,
            sc.set_name,
            c.card_number,
            c.name AS card_name,
            c.pokemon_name,
            c.rarity,
            c.holo_pattern
        FROM card_inventory ci
        JOIN cards c ON c.id = ci.card_id
        JOIN set_catalog sc ON sc.id = c.set_catalog_id
        WHERE 1 = 1
            {sale_status_filter}
            AND LOWER(COALESCE(ci.condition, '')) != 'graded'
            {set_filter}
            {card_filter}
            {custom_inventory_filter}
        GROUP BY
            c.id,
            sc.language,
            sc.set_code,
            sc.set_name,
            c.card_number,
            c.name,
            c.pokemon_name,
            c.rarity,
            c.holo_pattern,
            c.source_sequence
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


def seller_location_filter(alias: str, seller_location_scope: str) -> str:
    if seller_location_scope == "us":
        return f"AND {alias}.item_location_country = 'US'"
    if seller_location_scope == "international":
        return f"AND {alias}.item_location_country IS NOT NULL AND {alias}.item_location_country != 'US'"
    return ""


def listing_condition_filter(alias: str, args: argparse.Namespace) -> str:
    filters = []
    if args.listing_card_condition:
        filters.append(f"AND {alias}.card_condition = :listing_card_condition")
    if args.match_inventory_condition:
        filters.append(
            f"""
            AND EXISTS (
                SELECT 1
                FROM card_inventory ci_condition
                WHERE ci_condition.card_id = mlm.card_id
                    AND ci_condition.sale_status != 'reference'
                    AND LOWER(COALESCE(ci_condition.condition, '')) != 'graded'
                    AND {alias}.card_condition = ci_condition.condition
            )
            """
        )
    return "\n".join(filters)


def fetch_raw_price_map(args: argparse.Namespace, seller_location_scope: str = "aggregate") -> dict[int, dict[str, object]]:
    observations: dict[int, list[tuple[str, int]]] = {}
    marketplace_location_filter = seller_location_filter("ml", seller_location_scope)
    variation_location_filter = seller_location_filter("migv", seller_location_scope)
    marketplace_condition_filter = listing_condition_filter("ml", args)
    params = {"listing_card_condition": args.listing_card_condition} if args.listing_card_condition else {}
    with sqlite3.connect(args.db_path) as conn:
        conn.row_factory = sqlite3.Row
        if args.pricing_source in {"marketplace", "combined"}:
            for row in conn.execute(
                f"""
                WITH latest_snapshots AS (
                    SELECT mps.card_id, mps.fetch_run_id
                    FROM marketplace_price_snapshots mps
                    JOIN (
                        SELECT card_id, MAX(id) AS latest_snapshot_id
                        FROM marketplace_price_snapshots
                        GROUP BY card_id
                    ) latest ON latest.latest_snapshot_id = mps.id
                )
                SELECT DISTINCT mlm.card_id, ml.id AS listing_id, ml.total_price_cents
                FROM marketplace_listing_single_matches mlm
                JOIN marketplace_listings_singles ml ON ml.id = mlm.listing_id
                JOIN latest_snapshots ls ON ls.card_id = mlm.card_id
                    AND ls.fetch_run_id = ml.fetch_run_id
                WHERE mlm.match_status = 'accepted'
                    AND ml.total_price_cents IS NOT NULL
                    AND LOWER(COALESCE(ml.condition, '')) != 'graded'
                    {marketplace_location_filter}
                    {marketplace_condition_filter}
                """
                ,
                params,
            ):
                observations.setdefault(int(row["card_id"]), []).append(("marketplace", int(row["total_price_cents"])))

        if args.pricing_source in {"variations", "combined"}:
            for row in conn.execute(
                f"""
                WITH latest_snapshots AS (
                    SELECT mvps.card_id, mvps.fetch_run_id
                    FROM marketplace_variation_price_snapshots mvps
                    JOIN (
                        SELECT card_id, MAX(id) AS latest_snapshot_id
                        FROM marketplace_variation_price_snapshots
                        GROUP BY card_id
                    ) latest ON latest.latest_snapshot_id = mvps.id
                )
                SELECT DISTINCT migvm.card_id, migv.id AS variation_id, migv.price_cents
                FROM marketplace_item_group_variation_matches migvm
                JOIN marketplace_item_group_variations migv ON migv.id = migvm.item_group_variation_id
                JOIN latest_snapshots ls ON ls.card_id = migvm.card_id
                    AND ls.fetch_run_id = migvm.fetch_run_id
                WHERE migv.price_cents IS NOT NULL
                    AND UPPER(COALESCE(migv.estimated_availability_status, '')) != 'OUT_OF_STOCK'
                    AND COALESCE(migv.estimated_available_quantity, 1) > 0
                    {variation_location_filter}
                """
            ):
                observations.setdefault(int(row["card_id"]), []).append(
                    ("variations", int(row["price_cents"]) + args.shipping_cents)
                )

    price_map: dict[int, dict[str, object]] = {}
    for card_id, values in observations.items():
        prices = [price for _, price in values]
        stats = two_pass_stats_for_prices(prices)
        marketplace_count = sum(1 for source, _ in values if source == "marketplace")
        variation_count = sum(1 for source, _ in values if source == "variations")
        stats.update(
            {
                "pricing_source_used": args.pricing_source + "_raw",
                "marketplace_listing_count": marketplace_count,
                "variation_listing_count": variation_count,
                "seller_location_scope": seller_location_scope,
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
                "seller_location_scope": "",
                "listing_count": None,
                "original_listing_count": None,
                "outlier_listing_count": 0,
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


def fetch_rows(args: argparse.Namespace, seller_location_scope: str = "aggregate") -> list[dict[str, object]]:
    use_raw_recalculation = args.recalculate_from_raw or not args.use_snapshot_tables
    if args.pricing_source == "combined" and not use_raw_recalculation:
        print("Combined snapshot mode is approximate. Use --recalculate-from-raw for true combined percentiles.")
    inventory_rows = fetch_inventory_rows(
        args.set_code,
        args.db_path,
        card_id=args.card_id,
        include_reference=args.include_reference,
        inventory_where=args.inventory_where,
    )
    price_map = (
        fetch_raw_price_map(args, seller_location_scope=seller_location_scope)
        if use_raw_recalculation
        else fetch_snapshot_price_map(args)
    )
    rows = attach_price_data(inventory_rows, price_map)
    return apply_workbook_order(rows, args.order_workbook, args.order_sheet)


def workbook_order_map(path: Path, sheet_name: str) -> dict[int, int]:
    workbook_path = path if path.is_absolute() else ROOT / path
    workbook = load_workbook(workbook_path, read_only=True, data_only=True)
    if sheet_name not in workbook.sheetnames:
        raise SystemExit(f"Sheet {sheet_name!r} was not found in {workbook_path}.")
    sheet = workbook[sheet_name]
    headers = {
        str(sheet.cell(1, column).value or "").strip(): column
        for column in range(1, sheet.max_column + 1)
    }
    card_id_column = headers.get("Matched Card ID")
    if not card_id_column:
        raise SystemExit(f"{workbook_path} does not have a 'Matched Card ID' column.")

    order = {}
    for row_number in range(2, sheet.max_row + 1):
        value = sheet.cell(row_number, card_id_column).value
        if value in (None, ""):
            continue
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        try:
            card_id = int(value)
        except (TypeError, ValueError):
            continue
        order.setdefault(card_id, row_number)
    return order


def apply_workbook_order(
    rows: list[dict[str, object]],
    workbook_path: Path | None,
    sheet_name: str,
) -> list[dict[str, object]]:
    if not workbook_path:
        return rows
    order = workbook_order_map(workbook_path, sheet_name)
    for row in rows:
        row["binder_row"] = order.get(int(row["card_id"]), 999999)
    return sorted(rows, key=lambda row: (int(row.get("binder_row") or 999999), int(row["card_id"])))


def populate_xlsx_sheet(workbook: Workbook, sheet_name: str, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    sheet = workbook.active if workbook.active.max_row == 1 and workbook.active.max_column == 1 and workbook.active["A1"].value is None else workbook.create_sheet()
    sheet.title = sheet_name
    sheet.freeze_panes = "A2"

    header_fill = PatternFill("solid", fgColor="1F2937")
    header_font = Font(bold=True, color="FFFFFF")
    metric_fill = PatternFill("solid", fgColor=METRIC_COLUMN_FILL)
    good_price_fill = PatternFill("solid", fgColor=GOOD_PRICE_FILL)
    review_fills = {
        flag: PatternFill("solid", fgColor=color)
        for flag, color in REVIEW_FILLS.items()
    }
    no_data_fill = review_fills["No Data"]
    no_data_font = Font(color="FFFFFF")

    for column_number, header in enumerate(fieldnames, start=1):
        cell = sheet.cell(1, column_number, header)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    metric_columns = {
        "p25_total_cents",
        "p25_total",
        "median_total_cents",
        "median_total",
    }
    metric_indexes = {
        fieldnames.index(header) + 1
        for header in metric_columns
        if header in fieldnames
    }
    review_flag_index = fieldnames.index("REVIEW_FLAG") + 1
    p25_price_index = fieldnames.index("P25_LISTING_PRICE") + 1
    blended_price_index = fieldnames.index("P25_MEDIAN_LISTING_PRICE") + 1

    for row_number, row in enumerate(rows, start=2):
        review_flag = str(row.get("REVIEW_FLAG") or "")
        is_no_data = review_flag == "No Data"
        row_fill = review_fills.get(review_flag)
        for column_number, header in enumerate(fieldnames, start=1):
            cell = sheet.cell(row_number, column_number, row.get(header))
            if row_fill:
                cell.fill = row_fill
            if column_number in metric_indexes:
                cell.fill = metric_fill
            if is_no_data:
                cell.fill = no_data_fill
                cell.font = no_data_font
            if header.endswith("_cents") or header in {
                "listing_count",
                "original_listing_count",
                "outlier_listing_count",
                "marketplace_listing_count",
                "variation_listing_count",
                "quantity",
            }:
                cell.number_format = "0.00" if header == "stddev_total_cents" else "0"
            cell.alignment = Alignment(vertical="top", wrap_text=False)

        sheet.cell(row_number, review_flag_index).font = Font(bold=True)
        if is_no_data:
            sheet.cell(row_number, review_flag_index).font = Font(bold=True, color="FFFFFF")
        if not is_no_data and row.get("P25_REVIEW_FLAG") == "OK":
            sheet.cell(row_number, p25_price_index).fill = good_price_fill
        if not is_no_data and row.get("P25_MEDIAN_REVIEW_FLAG") == "OK":
            sheet.cell(row_number, blended_price_index).fill = good_price_fill

    for column_number in metric_indexes:
        sheet.cell(1, column_number).fill = metric_fill
        sheet.cell(1, column_number).font = Font(bold=True, color="000000")

    widths = {
        "A": 10,
        "B": 9,
        "C": 16,
        "D": 10,
        "E": 24,
        "F": 14,
        "G": 26,
        "H": 22,
        "I": 18,
        "J": 16,
        "K": 18,
        "L": 12,
        "M": 10,
        "N": 12,
        "O": 12,
    }
    header_widths = {
        "REVIEW_FLAG": 13,
        "REVIEW_REASONS": 42,
        "snapshot_created_at": 20,
        "p25_total_cents": 13,
        "p25_total": 11,
        "median_total_cents": 15,
        "median_total": 13,
        "P25_LISTING_PRICE_CENTS": 18,
        "P25_LISTING_PRICE": 16,
        "P25_MEDIAN_LISTING_PRICE_CENTS": 24,
        "P25_MEDIAN_LISTING_PRICE": 22,
    }
    for column_number, header in enumerate(fieldnames, start=1):
        letter = get_column_letter(column_number)
        sheet.column_dimensions[letter].width = widths.get(letter, header_widths.get(header, 14))

    sheet.auto_filter.ref = f"A1:{get_column_letter(len(fieldnames))}{len(rows) + 1}"


def write_xlsx_report(rows: list[dict[str, object]], fieldnames: list[str], output_path: Path) -> None:
    workbook = Workbook()
    populate_xlsx_sheet(workbook, "Profit Estimate", rows, fieldnames)
    workbook.save(output_path)


def write_multi_sheet_xlsx_report(sheets: list[tuple[str, list[dict[str, object]]]], fieldnames: list[str], output_path: Path) -> None:
    workbook = Workbook()
    for sheet_name, rows in sheets:
        populate_xlsx_sheet(workbook, sheet_name, rows, fieldnames)
    workbook.save(output_path)


def write_report(
    rows: list[dict[str, object]],
    args: argparse.Namespace,
    output_path: Path,
    write_xlsx: bool = True,
) -> tuple[int, int, int, list[dict[str, object]], list[str]]:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    total_quantity = 0
    total_gross_cents = 0
    total_net_cents = 0

    fieldnames = [
        "binder_row",
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
        "seller_location_scope",
        "listing_count",
        "original_listing_count",
        "outlier_listing_count",
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
        "P25_LISTING_PRICE_CENTS",
        "P25_LISTING_PRICE",
        "P25_MEDIAN_LISTING_PRICE_CENTS",
        "P25_MEDIAN_LISTING_PRICE",
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
        "P25_REVIEW_FLAG",
        "P25_REVIEW_REASONS",
        "P25_MEDIAN_REVIEW_FLAG",
        "P25_MEDIAN_REVIEW_REASONS",
        "REVIEW_FLAG",
        "REVIEW_REASONS",
    ]

    output_rows = []
    for row in rows:
        quantity = int(row["quantity"])
        p25_total_cents = row["p25_total_cents"]

        if p25_total_cents is None:
            p25_listing_price_cents = 0
        else:
            p25_listing_price_cents = estimate_unit_gross_cents(
                p25_total_cents=p25_total_cents,
                shipping_cents=args.shipping_cents,
                floor_increment_cents=args.floor_increment_cents,
                minimum_cents=args.minimum_cents,
            )

        p25_median_listing_price_cents = estimate_blended_listing_price_cents(
            p25_total_cents=row["p25_total_cents"],
            median_total_cents=row["median_total_cents"],
            shipping_cents=args.shipping_cents,
            increment_cents=args.floor_increment_cents,
            minimum_cents=args.minimum_cents,
        )
        unit_gross_cents = p25_median_listing_price_cents

        unit_fee_cents = round(unit_gross_cents * args.marketplace_fee_rate)
        unit_net_cents = unit_gross_cents - unit_fee_cents
        total_row_gross_cents = unit_gross_cents * quantity
        total_row_fee_cents = unit_fee_cents * quantity
        total_row_net_cents = unit_net_cents * quantity
        p25_review_flag, p25_review_reasons = review_flag_and_reasons(row, p25_listing_price_cents, args.shipping_cents)
        p25_median_review_flag, p25_median_review_reasons = review_flag_and_reasons(
            row,
            p25_median_listing_price_cents,
            args.shipping_cents,
        )
        review_flag, review_reasons = p25_median_review_flag, p25_median_review_reasons
        if not row["listing_count"] or row["p25_total_cents"] is None:
            p25_review_flag = "No Data"
            p25_review_reasons = "no accepted marketplace pricing data; manual lookup required"
            p25_median_review_flag = "No Data"
            p25_median_review_reasons = p25_review_reasons
            review_flag = "No Data"
            review_reasons = p25_review_reasons

        total_quantity += quantity
        total_gross_cents += total_row_gross_cents
        total_net_cents += total_row_net_cents

        output_rows.append(
            {
                "card_id": row["card_id"],
                "binder_row": row.get("binder_row", ""),
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
                "seller_location_scope": row["seller_location_scope"],
                "listing_count": row["listing_count"],
                "original_listing_count": row["original_listing_count"],
                "outlier_listing_count": row["outlier_listing_count"],
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
                "stddev_total_cents": round_or_none(row["stddev_total_cents"]),
                "stddev_total": cents_to_dollars(row["stddev_total_cents"]),
                "estimated_shipping_cents": args.shipping_cents,
                "estimated_shipping": cents_to_dollars(args.shipping_cents),
                "P25_LISTING_PRICE_CENTS": p25_listing_price_cents,
                "P25_LISTING_PRICE": cents_to_dollars(p25_listing_price_cents),
                "P25_MEDIAN_LISTING_PRICE_CENTS": p25_median_listing_price_cents,
                "P25_MEDIAN_LISTING_PRICE": cents_to_dollars(p25_median_listing_price_cents),
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
                "P25_REVIEW_FLAG": p25_review_flag,
                "P25_REVIEW_REASONS": p25_review_reasons,
                "P25_MEDIAN_REVIEW_FLAG": p25_median_review_flag,
                "P25_MEDIAN_REVIEW_REASONS": p25_median_review_reasons,
                "REVIEW_FLAG": review_flag,
                "REVIEW_REASONS": review_reasons,
            }
        )

    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        writer.writerows(output_rows)

    if write_xlsx:
        write_xlsx_report(output_rows, fieldnames, output_path.with_suffix(".xlsx"))

    return total_quantity, total_gross_cents, total_net_cents, output_rows, fieldnames


def main() -> None:
    args = parse_args()

    if args.output:
        output_path = Path(args.output)
        if not output_path.is_absolute():
            output_path = ROOT / output_path
    else:
        label = args.report_label
        if not label:
            label = f"{args.set_code}_inventory_profit_estimate" if args.set_code else ""
        if not label and args.card_id:
            label = f"card_{args.card_id}_inventory_profit_estimate"
        if not label and args.inventory_where:
            label = "inventory_filtered_profit_estimate"
        if not label:
            label = "inventory_profit_estimate"
        output_path = timestamped_report_dir("inventory_profit_estimate", label) / "inventory_profit_estimate.tsv"

    if args.seller_location_split:
        args.recalculate_from_raw = True
        scopes = [
            ("us_sellers", "us"),
            ("international_sellers", "international"),
            ("aggregate", "aggregate"),
        ]
        totals = {}
        workbook_sheets = []
        workbook_fieldnames = None
        for suffix, scope in scopes:
            rows = fetch_rows(args, seller_location_scope=scope)
            if not rows:
                raise SystemExit("No inventory rows found for the requested filters.")
            scoped_output_path = output_path.with_name(f"{output_path.stem}_{suffix}{output_path.suffix}")
            total_quantity, total_gross_cents, total_net_cents, output_rows, fieldnames = write_report(
                rows,
                args,
                scoped_output_path,
                write_xlsx=False,
            )
            totals[suffix] = (total_quantity, total_gross_cents, total_net_cents)
            workbook_fieldnames = fieldnames
            sheet_name = {
                "us_sellers": "US Sellers",
                "international_sellers": "International Sellers",
                "aggregate": "Aggregate",
            }[suffix]
            workbook_sheets.append((sheet_name, output_rows))
            print(scoped_output_path)
        if workbook_fieldnames is not None:
            write_multi_sheet_xlsx_report(workbook_sheets, workbook_fieldnames, output_path.with_suffix(".xlsx"))
            print(output_path.with_suffix(".xlsx"))
        aggregate_total = totals["aggregate"]
        print(f"Cards with inventory: {len(fetch_rows(args, seller_location_scope='aggregate'))}")
        print(f"Total quantity: {aggregate_total[0]}")
        print(f"Total gross after shipping: {cents_to_dollars(aggregate_total[1])}")
        print(f"Total net after {args.marketplace_fee_rate:.4f} marketplace fee: {cents_to_dollars(aggregate_total[2])}")
        return

    rows = fetch_rows(args)
    if not rows:
        raise SystemExit("No inventory rows found for the requested filters.")

    total_quantity, total_gross_cents, total_net_cents, _, _ = write_report(rows, args, output_path)

    print(f"Cards with inventory: {len(rows)}")
    print(f"Total quantity: {total_quantity}")
    print(f"Total gross after shipping: {cents_to_dollars(total_gross_cents)}")
    print(f"Total net after {args.marketplace_fee_rate:.4f} marketplace fee: {cents_to_dollars(total_net_cents)}")
    print(output_path)


if __name__ == "__main__":
    main()
