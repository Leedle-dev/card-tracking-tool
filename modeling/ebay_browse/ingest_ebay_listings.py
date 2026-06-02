from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
import argparse
import csv
import json
import statistics
import sys

from sqlalchemy import select


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from card_tracker.db import session_scope
from card_tracker.db.models import (
    MarketplaceListing,
    MarketplaceListingFetchRun,
    MarketplaceListingMatch,
    MarketplaceListingQuery,
    MarketplacePriceSnapshot,
    MarketplaceSource,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest eBay listing TSV output into SQLite.")
    # Example:
    #   python modeling/ebay_browse/ingest_ebay_listings.py --run-dir modeling/ebay_browse/output/20260602_000000_cbb5c_gem_pack_vol_5
    parser.add_argument("--run-dir", required=True, type=Path, help="Timestamped eBay output directory to ingest.")
    parser.add_argument(
        "--db-path",
        type=Path,
        default=ROOT / "data" / "card_tracker.sqlite",
        help="Path to the local SQLite database.",
    )
    return parser.parse_args()


def cents_from_decimal_text(text: str | None) -> int | None:
    if text is None or not str(text).strip():
        return None
    try:
        value = Decimal(str(text).replace(",", "").strip())
    except InvalidOperation:
        return None
    return int((value * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def int_from_text(text: str | None) -> int | None:
    if text is None or not str(text).strip():
        return None
    try:
        return int(Decimal(str(text).replace(",", "").strip()))
    except InvalidOperation:
        return None


def float_from_text(text: str | None) -> float | None:
    if text is None or not str(text).strip():
        return None
    try:
        return float(str(text).replace(",", "").strip())
    except ValueError:
        return None


def bool_int(text: str | None) -> int:
    return 1 if str(text).strip().lower() == "true" else 0


def read_tsv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8") as file:
        return list(csv.DictReader(file, delimiter="\t"))


def load_metadata(run_dir: Path) -> dict[str, object]:
    matches = sorted(run_dir.glob("*_ebay_listings_metadata.json"))
    if not matches:
        raise SystemExit(f"No *_ebay_listings_metadata.json file found in {run_dir}")
    if len(matches) > 1:
        raise SystemExit(f"Multiple metadata files found in {run_dir}; expected exactly one.")
    return json.loads(matches[0].read_text(encoding="utf-8"))


def marketplace_source_id(session) -> int:
    source = session.execute(select(MarketplaceSource).where(MarketplaceSource.name == "eBay")).scalar_one_or_none()
    if source is None:
        source = MarketplaceSource(name="eBay", website_url="https://www.ebay.com", notes="Marketplace pricing source.")
        session.add(source)
        session.flush()
    return source.id


def listing_from_row(row: dict[str, str], fetch_run_id: int, source_id: int, raw_json_path: str | None) -> MarketplaceListing:
    price_cents = cents_from_decimal_text(row.get("price_value"))
    shipping_cents = cents_from_decimal_text(row.get("shipping_value"))
    total_price_cents = cents_from_decimal_text(row.get("total_value"))
    if total_price_cents is None and price_cents is not None and shipping_cents is not None:
        total_price_cents = price_cents + shipping_cents

    return MarketplaceListing(
        fetch_run_id=fetch_run_id,
        source_id=source_id,
        external_item_id=row["item_id"],
        legacy_item_id=row.get("legacy_item_id") or None,
        item_web_url=row.get("item_web_url") or None,
        title=row.get("title") or "",
        condition=row.get("condition") or None,
        buying_options=row.get("buying_options") or None,
        price_cents=price_cents,
        shipping_cents=shipping_cents,
        total_price_cents=total_price_cents,
        currency=row.get("price_currency") or row.get("total_currency") or "USD",
        is_variation_listing=bool_int(row.get("is_variation_listing")),
        item_group_href=row.get("item_group_href") or None,
        item_group_type=row.get("item_group_type") or None,
        item_location_country=row.get("item_location_country") or None,
        seller_feedback_score=int_from_text(row.get("seller_feedback_score")),
        seller_feedback_percentage=float_from_text(row.get("seller_feedback_percentage")),
        item_creation_date=row.get("item_creation_date") or None,
        item_end_date=row.get("item_end_date") or None,
        image_url=row.get("image_url") or None,
        raw_json_path=raw_json_path,
    )


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


def snapshot_for_card(fetch_run_id: int, card_id: int, listings: list[MarketplaceListing]) -> MarketplacePriceSnapshot:
    prices = [listing.total_price_cents for listing in listings if listing.total_price_cents is not None]
    domestic_count = sum(1 for listing in listings if listing.item_location_country == "US")
    international_count = sum(1 for listing in listings if listing.item_location_country and listing.item_location_country != "US")
    p25 = percentile(prices, 0.25)
    p75 = percentile(prices, 0.75)

    return MarketplacePriceSnapshot(
        fetch_run_id=fetch_run_id,
        card_id=card_id,
        listing_count=len(listings),
        min_total_cents=min(prices) if prices else None,
        max_total_cents=max(prices) if prices else None,
        mean_total_cents=float(statistics.mean(prices)) if prices else None,
        median_total_cents=float(statistics.median(prices)) if prices else None,
        stddev_total_cents=float(statistics.stdev(prices)) if len(prices) > 1 else 0.0 if prices else None,
        p10_total_cents=percentile(prices, 0.10),
        p25_total_cents=p25,
        p75_total_cents=p75,
        p90_total_cents=percentile(prices, 0.90),
        iqr_total_cents=(p75 - p25) if p25 is not None and p75 is not None else None,
        trimmed_mean_total_cents=trimmed_mean(prices),
        domestic_listing_count=domestic_count,
        international_listing_count=international_count,
    )


def ingest_run(run_dir: Path, db_path: Path) -> dict[str, int]:
    metadata = load_metadata(run_dir)
    files = metadata["files"]
    query_metadata = {str(query["label"]): query for query in metadata["queries"]}
    completed_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    rows_by_status = [
        ("accepted", read_tsv(Path(str(files["filtered"])))),
        ("rejected", read_tsv(Path(str(files["rejected"])))),
        ("variation", read_tsv(Path(str(files["variations"])))),
    ]

    with session_scope(db_path=db_path) as session:
        source_id = marketplace_source_id(session)
        fetch_run = MarketplaceListingFetchRun(
            marketplace_source_id=source_id,
            set_catalog_id=int(metadata["set_catalog_id"]) if metadata.get("set_catalog_id") else None,
            started_at=str(metadata["timestamp"]),
            completed_at=completed_at,
            query_limit=int(metadata["query_limit"]),
            query_count=int(metadata["query_count"]),
            output_dir=str(run_dir),
            notes="Ingested from eBay Browse TSV output.",
        )
        session.add(fetch_run)
        session.flush()

        query_by_label: dict[str, MarketplaceListingQuery] = {}
        for label, query in query_metadata.items():
            query_row = MarketplaceListingQuery(
                fetch_run_id=fetch_run.id,
                card_id=int(query["card_id"]),
                query_text=str(query["query_text"]),
                result_total=int(query["result_total"]),
                result_exported=int(query["result_exported"]),
                accepted_count=int(query["accepted_count"]),
                rejected_count=int(query["rejected_count"]),
                variation_count=int(query["variation_count"]),
            )
            session.add(query_row)
            query_by_label[label] = query_row
        session.flush()

        listing_by_item_id: dict[str, MarketplaceListing] = {}
        accepted_listings_by_card: dict[int, list[MarketplaceListing]] = {}
        match_count = 0

        for status, rows in rows_by_status:
            for row in rows:
                label = row.get("query_label") or row.get("first_seen_query_label")
                if not label or label not in query_by_label:
                    continue

                query_row = query_by_label[label]
                query_info = query_metadata[label]
                item_id = row["item_id"]
                listing = listing_by_item_id.get(item_id)
                if listing is None:
                    listing = listing_from_row(
                        row,
                        fetch_run.id,
                        source_id,
                        raw_json_path=str(query_info.get("raw_json_path") or ""),
                    )
                    session.add(listing)
                    session.flush()
                    listing_by_item_id[item_id] = listing

                match = MarketplaceListingMatch(
                    listing_id=listing.id,
                    query_id=query_row.id,
                    card_id=query_row.card_id,
                    match_status=status,
                    filter_reasons=row.get("filter_reasons") or None,
                    filter_warnings=row.get("filter_warnings") or None,
                )
                session.add(match)
                match_count += 1

                if status == "accepted":
                    accepted_listings_by_card.setdefault(query_row.card_id, []).append(listing)

        for query_row in query_by_label.values():
            snapshot = snapshot_for_card(
                fetch_run.id,
                query_row.card_id,
                accepted_listings_by_card.get(query_row.card_id, []),
            )
            session.add(snapshot)

        return {
            "fetch_run_id": fetch_run.id,
            "queries": len(query_by_label),
            "listings": len(listing_by_item_id),
            "matches": match_count,
            "price_snapshots": len(query_by_label),
        }


def main() -> None:
    args = parse_args()
    result = ingest_run(run_dir=args.run_dir, db_path=args.db_path)
    print(
        f"Ingested fetch_run_id={result['fetch_run_id']} "
        f"queries={result['queries']} "
        f"listings={result['listings']} "
        f"matches={result['matches']} "
        f"price_snapshots={result['price_snapshots']}"
    )


if __name__ == "__main__":
    main()
