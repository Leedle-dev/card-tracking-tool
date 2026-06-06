from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
import argparse
import csv
import json
import re
import statistics
import sys

from sqlalchemy import func, select, text


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
    MarketplaceVariationPriceSnapshot,
    MarketplaceSource,
    Card,
    SetCatalog,
)
from fetch_ebay_listings import build_query
from fetch_houndoom_browse import search_query_text


LISTING_UPDATE_FIELDS = [
    "fetch_run_id",
    "legacy_item_id",
    "item_web_url",
    "title",
    "condition",
    "buying_options",
    "price_cents",
    "shipping_cents",
    "total_price_cents",
    "currency",
    "is_variation_listing",
    "item_group_href",
    "item_group_type",
    "item_location_country",
    "seller_feedback_score",
    "seller_feedback_percentage",
    "item_creation_date",
    "item_end_date",
    "image_url",
    "raw_json_path",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest eBay listing TSV output into SQLite.")
    # Example:
    #   python modeling/ebay_browse/ingest_ebay_listings.py --run-dir modeling/ebay_browse/output/20260602_000000_cbb5c_gem_pack_vol_5
    parser.add_argument("--run-dir", required=True, type=Path, help="Timestamped eBay output directory to ingest.")
    parser.add_argument("--set-code", help="Fallback set code for older run folders without metadata.")
    parser.add_argument("--set-name", help="Fallback set name for older run folders without metadata.")
    parser.add_argument(
        "--allow-duplicate",
        action="store_true",
        help="Allow ingesting a run folder that is already recorded in SQLite.",
    )
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


def nonnegative_int_from_text(text: str | None) -> int | None:
    value = int_from_text(text)
    if value is None or value < 0:
        return None
    return value


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


def find_one(run_dir: Path, pattern: str) -> Path:
    matches = sorted(run_dir.glob(pattern))
    if not matches:
        raise SystemExit(f"No {pattern} file found in {run_dir}")
    if len(matches) > 1:
        raise SystemExit(f"Multiple {pattern} files found in {run_dir}; expected exactly one.")
    return matches[0]


def load_metadata(run_dir: Path) -> dict[str, object] | None:
    matches = sorted(run_dir.glob("*_ebay_listings_metadata.json"))
    if not matches:
        return None
    if len(matches) > 1:
        raise SystemExit(f"Multiple metadata files found in {run_dir}; expected exactly one.")
    return json.loads(matches[0].read_text(encoding="utf-8"))


def load_fallback_queries(set_code: str, set_name: str, db_path: Path, limit: int) -> list[dict[str, object]]:
    with session_scope(db_path=db_path) as session:
        statement = (
            select(Card, SetCatalog)
            .join(SetCatalog, Card.set_catalog_id == SetCatalog.id)
            .where(func.lower(SetCatalog.set_code) == set_code.lower())
            .where(func.lower(SetCatalog.set_name) == set_name.lower())
            .order_by(Card.source_sequence, Card.card_number, Card.id)
        )
        rows = session.execute(statement).all()
        return [build_query(card, set_catalog, limit) for card, set_catalog in rows]


def load_run_rows(run_dir: Path, files: dict[str, str] | None = None) -> dict[str, list[dict[str, str]]]:
    if files:
        return {
            "accepted": read_tsv(Path(str(files["filtered"]))),
            "rejected": read_tsv(Path(str(files["rejected"]))),
            "variation": read_tsv(Path(str(files["variations"]))),
        }
    return {
        "accepted": read_tsv(find_one(run_dir, "*_ebay_listings_filtered.tsv")),
        "rejected": read_tsv(find_one(run_dir, "*_ebay_listings_rejected.tsv")),
        "variation": read_tsv(find_one(run_dir, "*_ebay_listings_variations.tsv")),
    }


def infer_timestamp(run_dir: Path) -> str:
    match = re.match(r"(\d{8}_\d{6})", run_dir.name)
    return match.group(1) if match else datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def fallback_metadata(run_dir: Path, db_path: Path, set_code: str | None, set_name: str | None) -> dict[str, object]:
    if not set_code or not set_name:
        raise SystemExit(
            "No metadata file found. Re-run with --set-code and --set-name to ingest older output folders."
        )

    rows_by_status = load_run_rows(run_dir)
    all_rows = rows_by_status["accepted"] + rows_by_status["rejected"] + rows_by_status["variation"]
    result_totals = {}
    exported_counts = {}
    accepted_counts = {}
    rejected_counts = {}
    variation_counts = {}
    for row in all_rows:
        label = row.get("query_label") or row.get("first_seen_query_label")
        if not label:
            continue
        result_totals[label] = max(result_totals.get(label, 0), int(row.get("result_count") or 0))
        exported_counts[label] = exported_counts.get(label, 0) + 1
    for row in rows_by_status["accepted"]:
        accepted_counts[row["query_label"]] = accepted_counts.get(row["query_label"], 0) + 1
    for row in rows_by_status["rejected"]:
        rejected_counts[row["query_label"]] = rejected_counts.get(row["query_label"], 0) + 1
    for row in rows_by_status["variation"]:
        label = row.get("first_seen_query_label") or row.get("query_label")
        variation_counts[label] = variation_counts.get(label, 0) + 1

    queries = load_fallback_queries(set_code, set_name, db_path, 200)
    query_metadata = []
    for query in queries:
        label = str(query["label"])
        if label not in result_totals and label not in accepted_counts and label not in rejected_counts and label not in variation_counts:
            continue
        raw_json = sorted((run_dir / "raw").glob(f"*_{label}.json"))
        query_metadata.append(
            {
                **query,
                "query_text": search_query_text(query),
                "result_total": result_totals.get(label, 0),
                "result_exported": exported_counts.get(label, 0),
                "accepted_count": accepted_counts.get(label, 0),
                "rejected_count": rejected_counts.get(label, 0),
                "variation_count": variation_counts.get(label, 0),
                "raw_json_path": str(raw_json[0]) if raw_json else "",
            }
        )

    if not query_metadata:
        raise SystemExit("Could not reconstruct query metadata for this run folder.")

    timestamp = infer_timestamp(run_dir)
    return {
        "timestamp": timestamp,
        "set_code": set_code,
        "set_name": set_name,
        "set_catalog_id": query_metadata[0].get("set_catalog_id"),
        "query_limit": 200,
        "query_count": len(query_metadata),
        "output_dir": str(run_dir),
        "files": None,
        "queries": query_metadata,
    }


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
        seller_feedback_score=nonnegative_int_from_text(row.get("seller_feedback_score")),
        seller_feedback_percentage=float_from_text(row.get("seller_feedback_percentage")),
        item_creation_date=row.get("item_creation_date") or None,
        item_end_date=row.get("item_end_date") or None,
        image_url=row.get("image_url") or None,
        raw_json_path=raw_json_path,
    )


def find_existing_listing(session, source_id: int, external_item_id: str) -> MarketplaceListing | None:
    return session.execute(
        select(MarketplaceListing)
        .where(MarketplaceListing.source_id == source_id)
        .where(MarketplaceListing.external_item_id == external_item_id)
        .order_by(MarketplaceListing.id.desc())
        .limit(1)
    ).scalar_one_or_none()


def apply_listing_update(existing: MarketplaceListing, incoming: MarketplaceListing) -> bool:
    changed = False
    for field in LISTING_UPDATE_FIELDS:
        incoming_value = getattr(incoming, field)
        if getattr(existing, field) != incoming_value:
            setattr(existing, field, incoming_value)
            changed = True
    return changed


def mirror_listing_to_split_table(session, listing: MarketplaceListing) -> None:
    params = {
        "id": listing.id,
        "fetch_run_id": listing.fetch_run_id,
        "source_id": listing.source_id,
        "external_item_id": listing.external_item_id,
        "legacy_item_id": listing.legacy_item_id,
        "item_web_url": listing.item_web_url,
        "title": listing.title,
        "condition": listing.condition,
        "buying_options": listing.buying_options,
        "price_cents": listing.price_cents,
        "shipping_cents": listing.shipping_cents,
        "total_price_cents": listing.total_price_cents,
        "currency": listing.currency,
        "item_group_href": listing.item_group_href,
        "item_group_type": listing.item_group_type,
        "item_location_country": listing.item_location_country,
        "seller_feedback_score": listing.seller_feedback_score,
        "seller_feedback_percentage": listing.seller_feedback_percentage,
        "item_creation_date": listing.item_creation_date,
        "item_end_date": listing.item_end_date,
        "image_url": listing.image_url,
        "raw_json_path": listing.raw_json_path,
        "checked_at": listing.checked_at,
        "created_at": listing.created_at,
    }

    if listing.is_variation_listing:
        session.execute(text("DELETE FROM marketplace_listings_singles WHERE id = :id"), {"id": listing.id})
        session.execute(
            text(
                """
                INSERT INTO marketplace_listings_variations (
                    id, fetch_run_id, source_id, external_item_id, legacy_item_id, item_web_url,
                    title, condition, buying_options, price_cents, shipping_cents, total_price_cents,
                    currency, item_group_href, item_group_type, item_location_country, seller_feedback_score,
                    seller_feedback_percentage, item_creation_date, item_end_date, image_url, raw_json_path,
                    checked_at, created_at
                )
                VALUES (
                    :id, :fetch_run_id, :source_id, :external_item_id, :legacy_item_id, :item_web_url,
                    :title, :condition, :buying_options, :price_cents, :shipping_cents, :total_price_cents,
                    :currency, :item_group_href, :item_group_type, :item_location_country, :seller_feedback_score,
                    :seller_feedback_percentage, :item_creation_date, :item_end_date, :image_url, :raw_json_path,
                    :checked_at, :created_at
                )
                ON CONFLICT(id) DO UPDATE SET
                    fetch_run_id = excluded.fetch_run_id,
                    source_id = excluded.source_id,
                    external_item_id = excluded.external_item_id,
                    legacy_item_id = excluded.legacy_item_id,
                    item_web_url = excluded.item_web_url,
                    title = excluded.title,
                    condition = excluded.condition,
                    buying_options = excluded.buying_options,
                    price_cents = excluded.price_cents,
                    shipping_cents = excluded.shipping_cents,
                    total_price_cents = excluded.total_price_cents,
                    currency = excluded.currency,
                    item_group_href = excluded.item_group_href,
                    item_group_type = excluded.item_group_type,
                    item_location_country = excluded.item_location_country,
                    seller_feedback_score = excluded.seller_feedback_score,
                    seller_feedback_percentage = excluded.seller_feedback_percentage,
                    item_creation_date = excluded.item_creation_date,
                    item_end_date = excluded.item_end_date,
                    image_url = excluded.image_url,
                    raw_json_path = excluded.raw_json_path,
                    checked_at = excluded.checked_at
                """
            ),
            params,
        )
        return

    session.execute(text("DELETE FROM marketplace_listings_variations WHERE id = :id"), {"id": listing.id})
    session.execute(
        text(
            """
            INSERT INTO marketplace_listings_singles (
                id, fetch_run_id, source_id, external_item_id, legacy_item_id, item_web_url,
                title, condition, buying_options, price_cents, shipping_cents, total_price_cents,
                currency, item_location_country, seller_feedback_score, seller_feedback_percentage,
                item_creation_date, item_end_date, image_url, raw_json_path, checked_at, created_at
            )
            VALUES (
                :id, :fetch_run_id, :source_id, :external_item_id, :legacy_item_id, :item_web_url,
                :title, :condition, :buying_options, :price_cents, :shipping_cents, :total_price_cents,
                :currency, :item_location_country, :seller_feedback_score, :seller_feedback_percentage,
                :item_creation_date, :item_end_date, :image_url, :raw_json_path, :checked_at, :created_at
            )
            ON CONFLICT(id) DO UPDATE SET
                fetch_run_id = excluded.fetch_run_id,
                source_id = excluded.source_id,
                external_item_id = excluded.external_item_id,
                legacy_item_id = excluded.legacy_item_id,
                item_web_url = excluded.item_web_url,
                title = excluded.title,
                condition = excluded.condition,
                buying_options = excluded.buying_options,
                price_cents = excluded.price_cents,
                shipping_cents = excluded.shipping_cents,
                total_price_cents = excluded.total_price_cents,
                currency = excluded.currency,
                item_location_country = excluded.item_location_country,
                seller_feedback_score = excluded.seller_feedback_score,
                seller_feedback_percentage = excluded.seller_feedback_percentage,
                item_creation_date = excluded.item_creation_date,
                item_end_date = excluded.item_end_date,
                image_url = excluded.image_url,
                raw_json_path = excluded.raw_json_path,
                checked_at = excluded.checked_at
            """
        ),
        params,
    )


def mirror_match_to_split_table(
    session,
    listing: MarketplaceListing,
    query_id: int,
    card_id: int,
    status: str,
    filter_reasons: str | None,
    filter_warnings: str | None,
) -> int:
    if listing.is_variation_listing:
        if status != "variation":
            return 0
        session.execute(
            text(
                """
                INSERT OR IGNORE INTO marketplace_listing_variation_matches (
                    listing_id, query_id, card_id, match_status, filter_reasons, filter_warnings
                )
                VALUES (:listing_id, :query_id, :card_id, 'variation', :filter_reasons, :filter_warnings)
                """
            ),
            {
                "listing_id": listing.id,
                "query_id": query_id,
                "card_id": card_id,
                "filter_reasons": filter_reasons,
                "filter_warnings": filter_warnings,
            },
        )
        return 1

    if status == "variation":
        return 0
    session.execute(
        text(
            """
            INSERT OR IGNORE INTO marketplace_listing_single_matches (
                listing_id, query_id, card_id, match_status, filter_reasons, filter_warnings
            )
            VALUES (:listing_id, :query_id, :card_id, :match_status, :filter_reasons, :filter_warnings)
            """
        ),
        {
            "listing_id": listing.id,
            "query_id": query_id,
            "card_id": card_id,
            "match_status": status,
            "filter_reasons": filter_reasons,
            "filter_warnings": filter_warnings,
        },
    )
    return 1


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


def variation_snapshot_for_card(
    fetch_run_id: int,
    card_id: int,
    listings: list[MarketplaceListing],
) -> MarketplaceVariationPriceSnapshot:
    prices = [listing.price_cents for listing in listings if listing.price_cents is not None]
    domestic_count = sum(1 for listing in listings if listing.item_location_country == "US")
    international_count = sum(1 for listing in listings if listing.item_location_country and listing.item_location_country != "US")
    p25 = percentile(prices, 0.25)
    p75 = percentile(prices, 0.75)

    return MarketplaceVariationPriceSnapshot(
        fetch_run_id=fetch_run_id,
        card_id=card_id,
        variation_listing_count=len(listings),
        min_price_cents=min(prices) if prices else None,
        max_price_cents=max(prices) if prices else None,
        mean_price_cents=float(statistics.mean(prices)) if prices else None,
        median_price_cents=float(statistics.median(prices)) if prices else None,
        stddev_price_cents=float(statistics.stdev(prices)) if len(prices) > 1 else 0.0 if prices else None,
        p10_price_cents=percentile(prices, 0.10),
        p25_price_cents=p25,
        p75_price_cents=p75,
        p90_price_cents=percentile(prices, 0.90),
        iqr_price_cents=(p75 - p25) if p25 is not None and p75 is not None else None,
        trimmed_mean_price_cents=trimmed_mean(prices),
        domestic_listing_count=domestic_count,
        international_listing_count=international_count,
    )


def ingest_run(
    run_dir: Path,
    db_path: Path,
    set_code: str | None = None,
    set_name: str | None = None,
    allow_duplicate: bool = False,
) -> dict[str, int]:
    metadata = load_metadata(run_dir)
    if metadata is None:
        metadata = fallback_metadata(run_dir, db_path, set_code, set_name)
    files = metadata["files"]
    query_metadata = {str(query["label"]): query for query in metadata["queries"]}
    completed_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    loaded_rows = load_run_rows(run_dir, files if isinstance(files, dict) else None)
    rows_by_status = [
        ("accepted", loaded_rows["accepted"]),
        ("rejected", loaded_rows["rejected"]),
        ("variation", loaded_rows["variation"]),
    ]

    with session_scope(db_path=db_path) as session:
        source_id = marketplace_source_id(session)
        existing_run = session.execute(
            select(MarketplaceListingFetchRun).where(MarketplaceListingFetchRun.output_dir == str(run_dir))
        ).scalar_one_or_none()
        if existing_run is not None and not allow_duplicate:
            raise SystemExit(
                f"Run folder is already ingested as fetch_run_id={existing_run.id}. "
                "Use --allow-duplicate only if you intentionally want another copy."
            )

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
        variation_listings_by_card: dict[int, list[MarketplaceListing]] = {}
        match_count = 0
        listings_created = 0
        listings_updated = 0
        listings_unchanged = 0
        split_matches = 0

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
                    incoming_listing = listing_from_row(
                        row,
                        fetch_run.id,
                        source_id,
                        raw_json_path=str(query_info.get("raw_json_path") or ""),
                    )
                    listing = find_existing_listing(session, source_id, item_id)
                    if listing is None:
                        listing = incoming_listing
                        session.add(listing)
                        session.flush()
                        listings_created += 1
                    elif apply_listing_update(listing, incoming_listing):
                        listings_updated += 1
                    else:
                        listings_unchanged += 1
                    mirror_listing_to_split_table(session, listing)
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
                split_matches += mirror_match_to_split_table(
                    session,
                    listing,
                    query_row.id,
                    query_row.card_id,
                    status,
                    row.get("filter_reasons") or None,
                    row.get("filter_warnings") or None,
                )

                if status == "accepted":
                    accepted_listings_by_card.setdefault(query_row.card_id, []).append(listing)
                elif status == "variation":
                    variation_listings_by_card.setdefault(query_row.card_id, []).append(listing)

        for query_row in query_by_label.values():
            snapshot = snapshot_for_card(
                fetch_run.id,
                query_row.card_id,
                accepted_listings_by_card.get(query_row.card_id, []),
            )
            session.add(snapshot)

            variation_snapshot = variation_snapshot_for_card(
                fetch_run.id,
                query_row.card_id,
                variation_listings_by_card.get(query_row.card_id, []),
            )
            session.add(variation_snapshot)

        return {
            "fetch_run_id": fetch_run.id,
            "queries": len(query_by_label),
            "listings": len(listing_by_item_id),
            "listings_created": listings_created,
            "listings_updated": listings_updated,
            "listings_unchanged": listings_unchanged,
            "matches": match_count,
            "split_matches": split_matches,
            "price_snapshots": len(query_by_label),
            "variation_price_snapshots": len(query_by_label),
        }


def main() -> None:
    args = parse_args()
    result = ingest_run(
        run_dir=args.run_dir,
        db_path=args.db_path,
        set_code=args.set_code,
        set_name=args.set_name,
        allow_duplicate=args.allow_duplicate,
    )
    print(
        f"Ingested fetch_run_id={result['fetch_run_id']} "
        f"queries={result['queries']} "
        f"listings={result['listings']} "
        f"listings_created={result['listings_created']} "
        f"listings_updated={result['listings_updated']} "
        f"listings_unchanged={result['listings_unchanged']} "
        f"matches={result['matches']} "
        f"split_matches={result['split_matches']} "
        f"price_snapshots={result['price_snapshots']}"
        f" variation_price_snapshots={result['variation_price_snapshots']}"
    )


if __name__ == "__main__":
    main()
