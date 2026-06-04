from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import argparse
import csv
import json
import re
import statistics
import sys

from sqlalchemy import delete, func, select


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from card_tracker.db import session_scope
from card_tracker.db.models import (
    Card,
    MarketplaceItemGroupVariation,
    MarketplaceListingFetchRun,
    MarketplaceSource,
    MarketplaceVariationPriceSnapshot,
    SetCatalog,
)
from fetch_houndoom_browse import (
    MARKETPLACE_ID,
    app_access_token,
    fetch_rate_limits,
    format_rate_limit_lines,
    normalized_search_text,
    request_bytes,
    title_has_card_number,
    title_has_phrase,
    title_has_token,
    value,
)
from ingest_ebay_listings import percentile, trimmed_mean


ITEM_GROUP_COLUMNS = [
    "item_group_id",
    "item_id",
    "legacy_item_id",
    "title",
    "condition",
    "buying_options",
    "variation_attributes_json",
    "variation_attributes_text",
    "price_value",
    "price_currency",
    "shipping_value",
    "shipping_currency",
    "total_value",
    "total_currency",
    "estimated_availability_status",
    "estimated_available_quantity",
    "is_available_for_pricing",
    "item_location_country",
    "image_url",
    "item_web_url",
    "raw_json_path",
]

MATCH_COLUMNS = [
    *ITEM_GROUP_COLUMNS,
    "card_id",
    "card_number",
    "pokemon_name",
    "card_name",
    "match_reasons",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch eBay Browse item-group variation children from a prior listing run."
    )
    # Example:
    #   python modeling/ebay_browse/fetch_ebay_item_groups.py --run-dir modeling/ebay_browse/output/20260604_144758_cbb5c_gem_pack_vol_5 --set-code CBB5C --set-name "Gem Pack Vol. 5" --ingest --update-snapshots
    parser.add_argument("--run-dir", required=True, type=Path, help="Timestamped eBay output directory.")
    parser.add_argument(
        "--variation-tsv",
        type=Path,
        help="Optional explicit *_ebay_listings_variations.tsv path. Defaults to the one in --run-dir.",
    )
    parser.add_argument(
        "--matches-tsv",
        type=Path,
        help="Optional existing *_item_group_matches.tsv to ingest/update snapshots without calling eBay.",
    )
    parser.add_argument("--set-code", help="Optional set code for set-specific matching, such as CBB5C.")
    parser.add_argument("--set-name", help='Optional set name for set-specific matching, such as "Gem Pack Vol. 5".')
    parser.add_argument("--max-groups", type=int, help="Optional safety cap for testing, such as --max-groups 5.")
    parser.add_argument("--dry-run", action="store_true", help="Print item-group URLs without calling eBay.")
    parser.add_argument("--ingest", action="store_true", help="Upsert fetched child variations into SQLite.")
    parser.add_argument(
        "--update-snapshots",
        action="store_true",
        help="Replace variation price snapshots for the ingested listing run using set-matched child rows.",
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=ROOT / "data" / "card_tracker.sqlite",
        help="Path to the local SQLite database.",
    )
    return parser.parse_args()


def find_one(run_dir: Path, pattern: str) -> Path:
    matches = sorted(run_dir.glob(pattern))
    if not matches:
        raise SystemExit(f"No {pattern} file found in {run_dir}")
    if len(matches) > 1:
        raise SystemExit(f"Multiple {pattern} files found in {run_dir}; expected exactly one.")
    return matches[0]


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as file:
        return list(csv.DictReader(file, delimiter="\t"))


def write_tsv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def item_group_id_from_href(href: str) -> str:
    parsed = urlparse(href)
    values = parse_qs(parsed.query).get("item_group_id")
    if values:
        return values[0]
    return Path(parsed.path).name


def load_item_group_hrefs(path: Path) -> list[tuple[str, str]]:
    groups: dict[str, str] = {}
    for row in read_tsv(path):
        href = row.get("item_group_href", "").strip()
        if not href:
            continue
        group_id = item_group_id_from_href(href)
        groups.setdefault(group_id, href)
    return sorted(groups.items())


def request_item_group(access_token: str, href: str) -> dict[str, object]:
    response = request_bytes(
        href,
        {
            "Authorization": f"Bearer {access_token}",
            "X-EBAY-C-MARKETPLACE-ID": MARKETPLACE_ID,
            "Accept": "application/json",
        },
    )
    return json.loads(response.decode("utf-8"))


def item_children(payload: dict[str, object]) -> list[dict[str, object]]:
    for key in ("items", "itemSummaries"):
        items = payload.get(key)
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]
    return []


def money_value(payload: object) -> str:
    return value(payload, "value") if isinstance(payload, dict) else ""


def money_currency(payload: object) -> str:
    return value(payload, "currency") if isinstance(payload, dict) else ""


def first_shipping_cost(item: dict[str, object]) -> dict[str, object]:
    options = item.get("shippingOptions")
    if not isinstance(options, list):
        return {}
    for option in options:
        if not isinstance(option, dict):
            continue
        shipping = option.get("shippingCost")
        if isinstance(shipping, dict):
            return shipping
    return {}


def availability(item: dict[str, object]) -> tuple[str, str]:
    rows = item.get("estimatedAvailabilities")
    if not isinstance(rows, list) or not rows:
        return "", ""
    first = rows[0] if isinstance(rows[0], dict) else {}
    return value(first, "estimatedAvailabilityStatus"), value(first, "estimatedAvailableQuantity")


def variation_attributes(item: dict[str, object]) -> tuple[str, str]:
    aspects = item.get("localizedAspects")
    if not isinstance(aspects, list):
        return "", ""
    parsed = []
    for aspect in aspects:
        if not isinstance(aspect, dict):
            continue
        name = value(aspect, "name")
        item_value = value(aspect, "value")
        if name or item_value:
            parsed.append({"name": name, "value": item_value})
    text = " ".join(f"{row['name']}: {row['value']}".strip(": ") for row in parsed)
    return json.dumps(parsed, ensure_ascii=True, sort_keys=True), text


def bool_for_pricing(status: str, quantity: str) -> bool:
    if status.upper() == "OUT_OF_STOCK":
        return False
    if quantity.strip():
        try:
            return int(Decimal(quantity.replace(",", ""))) > 0
        except InvalidOperation:
            return False
    return True


def flatten_child(item_group_id: str, item: dict[str, object], raw_json_path: Path) -> dict[str, object]:
    price = item.get("price") if isinstance(item.get("price"), dict) else {}
    total = item.get("totalPrice") if isinstance(item.get("totalPrice"), dict) else {}
    shipping = first_shipping_cost(item)
    location = item.get("itemLocation") if isinstance(item.get("itemLocation"), dict) else {}
    image = item.get("image") if isinstance(item.get("image"), dict) else {}
    status, quantity = availability(item)
    attributes_json, attributes_text = variation_attributes(item)
    return {
        "item_group_id": item_group_id,
        "item_id": value(item, "itemId"),
        "legacy_item_id": value(item, "legacyItemId"),
        "title": value(item, "title"),
        "condition": value(item, "condition"),
        "buying_options": ",".join(item.get("buyingOptions", []))
        if isinstance(item.get("buyingOptions"), list)
        else "",
        "variation_attributes_json": attributes_json,
        "variation_attributes_text": attributes_text,
        "price_value": money_value(price),
        "price_currency": money_currency(price),
        "shipping_value": money_value(shipping),
        "shipping_currency": money_currency(shipping),
        "total_value": money_value(total),
        "total_currency": money_currency(total),
        "estimated_availability_status": status,
        "estimated_available_quantity": quantity,
        "is_available_for_pricing": str(bool_for_pricing(status, quantity)),
        "item_location_country": value(location, "country"),
        "image_url": value(image, "imageUrl"),
        "item_web_url": value(item, "itemWebUrl"),
        "raw_json_path": str(raw_json_path),
    }


def cents_from_decimal_text(text: str | None) -> int | None:
    if text is None or not str(text).strip():
        return None
    try:
        value_decimal = Decimal(str(text).replace(",", "").strip())
    except InvalidOperation:
        return None
    return int((value_decimal * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def int_from_text(text: str | None) -> int | None:
    if text is None or not str(text).strip():
        return None
    try:
        return int(Decimal(str(text).replace(",", "").strip()))
    except InvalidOperation:
        return None


def marketplace_source_id(session) -> int:
    source = session.execute(select(MarketplaceSource).where(MarketplaceSource.name == "eBay")).scalar_one_or_none()
    if source is None:
        source = MarketplaceSource(name="eBay", website_url="https://www.ebay.com", notes="Marketplace pricing source.")
        session.add(source)
        session.flush()
    return source.id


def upsert_item_group_rows(rows: list[dict[str, object]], db_path: Path) -> dict[str, int]:
    checked_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    created = 0
    updated = 0
    unchanged = 0
    with session_scope(db_path=db_path) as session:
        source_id = marketplace_source_id(session)
        for row in rows:
            price_cents = cents_from_decimal_text(str(row.get("price_value") or ""))
            shipping_cents = cents_from_decimal_text(str(row.get("shipping_value") or ""))
            total_price_cents = cents_from_decimal_text(str(row.get("total_value") or ""))
            if total_price_cents is None and price_cents is not None and shipping_cents is not None:
                total_price_cents = price_cents + shipping_cents

            existing = session.execute(
                select(MarketplaceItemGroupVariation)
                .where(MarketplaceItemGroupVariation.source_id == source_id)
                .where(MarketplaceItemGroupVariation.item_group_id == str(row["item_group_id"]))
                .where(MarketplaceItemGroupVariation.external_item_id == str(row["item_id"]))
            ).scalar_one_or_none()
            if existing is None:
                session.add(
                    MarketplaceItemGroupVariation(
                        source_id=source_id,
                        item_group_id=str(row["item_group_id"]),
                        external_item_id=str(row["item_id"]),
                        legacy_item_id=str(row.get("legacy_item_id") or "") or None,
                        title=str(row.get("title") or ""),
                        condition=str(row.get("condition") or "") or None,
                        buying_options=str(row.get("buying_options") or "") or None,
                        variation_attributes_json=str(row.get("variation_attributes_json") or "") or None,
                        variation_attributes_text=str(row.get("variation_attributes_text") or "") or None,
                        price_cents=price_cents,
                        shipping_cents=shipping_cents,
                        total_price_cents=total_price_cents,
                        currency=str(row.get("price_currency") or row.get("total_currency") or "USD"),
                        estimated_availability_status=str(row.get("estimated_availability_status") or "") or None,
                        estimated_available_quantity=int_from_text(str(row.get("estimated_available_quantity") or "")),
                        item_location_country=str(row.get("item_location_country") or "") or None,
                        item_web_url=str(row.get("item_web_url") or "") or None,
                        image_url=str(row.get("image_url") or "") or None,
                        raw_json_path=str(row.get("raw_json_path") or "") or None,
                        first_seen_at=checked_at,
                        last_seen_at=checked_at,
                    )
                )
                created += 1
                continue

            changed = False
            updates = {
                "legacy_item_id": str(row.get("legacy_item_id") or "") or None,
                "title": str(row.get("title") or ""),
                "condition": str(row.get("condition") or "") or None,
                "buying_options": str(row.get("buying_options") or "") or None,
                "variation_attributes_json": str(row.get("variation_attributes_json") or "") or None,
                "variation_attributes_text": str(row.get("variation_attributes_text") or "") or None,
                "price_cents": price_cents,
                "shipping_cents": shipping_cents,
                "total_price_cents": total_price_cents,
                "currency": str(row.get("price_currency") or row.get("total_currency") or "USD"),
                "estimated_availability_status": str(row.get("estimated_availability_status") or "") or None,
                "estimated_available_quantity": int_from_text(str(row.get("estimated_available_quantity") or "")),
                "item_location_country": str(row.get("item_location_country") or "") or None,
                "item_web_url": str(row.get("item_web_url") or "") or None,
                "image_url": str(row.get("image_url") or "") or None,
                "raw_json_path": str(row.get("raw_json_path") or "") or None,
                "last_seen_at": checked_at,
            }
            for field, incoming in updates.items():
                if getattr(existing, field) != incoming:
                    setattr(existing, field, incoming)
                    changed = True
            if changed:
                updated += 1
            else:
                unchanged += 1
    return {"created": created, "updated": updated, "unchanged": unchanged}


def normalized_compact(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", normalized_search_text(text)).strip()


def search_blob(row: dict[str, object]) -> str:
    return " ".join(
        [
            str(row.get("title") or ""),
            str(row.get("variation_attributes_text") or ""),
            str(row.get("variation_attributes_json") or ""),
        ]
    )


def set_identity_matches(text: str, set_code: str, set_name: str) -> bool:
    if title_has_token(text, set_code):
        return True
    if title_has_phrase(text, set_name):
        return True
    compact_name = normalized_compact(set_name)
    compact_text = normalized_compact(text)
    return bool(compact_name and compact_name in compact_text)


def match_rows_to_set(
    rows: list[dict[str, object]],
    set_code: str,
    set_name: str,
    db_path: Path,
) -> list[dict[str, object]]:
    with session_scope(db_path=db_path) as session:
        card_rows = session.execute(
            select(
                Card.id,
                Card.card_number,
                Card.pokemon_name,
                Card.name,
            )
            .join(SetCatalog, Card.set_catalog_id == SetCatalog.id)
            .where(func.lower(SetCatalog.set_code) == set_code.lower())
            .where(func.lower(SetCatalog.set_name) == set_name.lower())
            .order_by(Card.source_sequence, Card.card_number, Card.id)
        ).all()

    cards = [
        {
            "id": row.id,
            "card_number": row.card_number,
            "pokemon_name": row.pokemon_name,
            "name": row.name,
        }
        for row in card_rows
    ]

    if not cards:
        raise SystemExit(f"No cards found for set_code={set_code!r} and set_name={set_name!r}.")

    matched_rows: list[dict[str, object]] = []
    for row in rows:
        if str(row.get("is_available_for_pricing")) != "True":
            continue
        text = search_blob(row)
        if not set_identity_matches(text, set_code, set_name):
            continue
        for card in cards:
            card_number = str(card["card_number"] or "")
            if not card_number or not title_has_card_number(text, card_number):
                continue
            pokemon_name = str(card["pokemon_name"] or card["name"])
            card_name = str(card["name"])
            reasons = [f"card_number:{card_number}"]
            if set_identity_matches(text, set_code, set_name):
                reasons.append(f"set_identity:{set_code}_or_{set_name}")
            if pokemon_name and title_has_phrase(text, pokemon_name):
                reasons.append(f"pokemon:{pokemon_name}")
            matched_rows.append(
                {
                    **row,
                    "card_id": card["id"],
                    "card_number": card_number,
                    "pokemon_name": pokemon_name,
                    "card_name": card_name,
                    "match_reasons": ";".join(reasons),
                }
            )
            break
    return matched_rows


def latest_fetch_run_id(run_dir: Path, db_path: Path) -> int:
    with session_scope(db_path=db_path) as session:
        fetch_run = session.execute(
            select(MarketplaceListingFetchRun)
            .where(MarketplaceListingFetchRun.output_dir == str(run_dir))
            .order_by(MarketplaceListingFetchRun.id.desc())
            .limit(1)
        ).scalar_one_or_none()
        if fetch_run is None:
            raise SystemExit(f"{run_dir} is not recorded in marketplace_listing_fetch_runs.")
        return fetch_run.id


def snapshot_tuple(fetch_run_id: int, card_id: int, rows: list[dict[str, object]]) -> MarketplaceVariationPriceSnapshot:
    prices = [
        cents
        for cents in (cents_from_decimal_text(str(row.get("price_value") or "")) for row in rows)
        if cents is not None
    ]
    domestic_count = sum(1 for row in rows if row.get("item_location_country") == "US")
    international_count = sum(
        1 for row in rows if row.get("item_location_country") and row.get("item_location_country") != "US"
    )
    p25 = percentile(prices, 0.25)
    p75 = percentile(prices, 0.75)
    return MarketplaceVariationPriceSnapshot(
        fetch_run_id=fetch_run_id,
        card_id=card_id,
        variation_listing_count=len(rows),
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


def update_variation_snapshots(
    fetch_run_id: int,
    matched_rows: list[dict[str, object]],
    db_path: Path,
) -> int:
    rows_by_card: dict[int, list[dict[str, object]]] = {}
    for row in matched_rows:
        rows_by_card.setdefault(int(row["card_id"]), []).append(row)

    with session_scope(db_path=db_path) as session:
        session.execute(
            delete(MarketplaceVariationPriceSnapshot).where(
                MarketplaceVariationPriceSnapshot.fetch_run_id == fetch_run_id
            )
        )
        for card_id, rows in rows_by_card.items():
            session.add(snapshot_tuple(fetch_run_id, card_id, rows))
    return len(rows_by_card)


def main() -> None:
    args = parse_args()

    if args.matches_tsv:
        matched_rows = read_tsv(args.matches_tsv)
        ingest_result = {"created": 0, "updated": 0, "unchanged": 0}
        snapshots_updated = 0
        if args.ingest:
            ingest_result = upsert_item_group_rows(matched_rows, args.db_path)
        if args.update_snapshots:
            fetch_run_id = latest_fetch_run_id(args.run_dir, args.db_path)
            snapshots_updated = update_variation_snapshots(fetch_run_id, matched_rows, args.db_path)

        print(f"Read {len(matched_rows)} matched item-group rows from {args.matches_tsv}")
        if args.ingest:
            print(
                "Ingested item-group variations: "
                f"{ingest_result['created']} created, "
                f"{ingest_result['updated']} updated, "
                f"{ingest_result['unchanged']} unchanged"
            )
        if args.update_snapshots:
            print(f"Updated variation price snapshots for {snapshots_updated} cards.")
        if not args.ingest and not args.update_snapshots:
            print("No database writes requested. Add --ingest and/or --update-snapshots to write to SQLite.")
        return

    variation_tsv = args.variation_tsv or find_one(args.run_dir, "*_ebay_listings_variations.tsv")
    item_groups = load_item_group_hrefs(variation_tsv)
    if args.max_groups is not None:
        item_groups = item_groups[: args.max_groups]

    if args.dry_run:
        for group_id, href in item_groups:
            print(f"{group_id}\t{href}")
        print(f"Found {len(item_groups)} unique item groups.")
        return

    output_dir = args.run_dir / "item_groups"
    raw_dir = output_dir / "raw"
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    access_token = app_access_token()
    rows: list[dict[str, object]] = []
    for group_id, href in item_groups:
        payload = request_item_group(access_token, href)
        raw_path = raw_dir / f"{timestamp}_{group_id}.json"
        raw_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        rows.extend(flatten_child(group_id, item, raw_path) for item in item_children(payload))

    available_rows = [row for row in rows if str(row.get("is_available_for_pricing")) == "True"]
    all_path = output_dir / f"{timestamp}_ebay_item_group_variations.tsv"
    available_path = output_dir / f"{timestamp}_ebay_item_group_variations_pricing.tsv"
    write_tsv(all_path, ITEM_GROUP_COLUMNS, rows)
    write_tsv(available_path, ITEM_GROUP_COLUMNS, available_rows)

    matched_rows: list[dict[str, object]] = []
    matched_path = None
    snapshots_updated = 0
    if args.set_code and args.set_name:
        matched_rows = match_rows_to_set(rows, args.set_code, args.set_name, args.db_path)
        set_label = re.sub(r"[^a-z0-9]+", "_", f"{args.set_code}_{args.set_name}".lower()).strip("_")
        matched_path = output_dir / f"{timestamp}_{set_label}_item_group_matches.tsv"
        write_tsv(matched_path, MATCH_COLUMNS, matched_rows)
        if args.update_snapshots:
            fetch_run_id = latest_fetch_run_id(args.run_dir, args.db_path)
            snapshots_updated = update_variation_snapshots(fetch_run_id, matched_rows, args.db_path)

    ingest_result = {"created": 0, "updated": 0, "unchanged": 0}
    if args.ingest:
        ingest_result = upsert_item_group_rows(rows, args.db_path)

    rate_limit_payload, rate_limit_error = fetch_rate_limits(access_token)
    rate_limit_lines = format_rate_limit_lines(rate_limit_payload, rate_limit_error)

    print(f"Fetched {len(item_groups)} item groups.")
    print(f"Wrote {len(rows)} child variation rows to {all_path}")
    print(f"Wrote {len(available_rows)} pricing-eligible rows to {available_path}")
    if matched_path:
        print(f"Wrote {len(matched_rows)} set-matched rows to {matched_path}")
    if args.ingest:
        print(
            "Ingested item-group variations: "
            f"{ingest_result['created']} created, "
            f"{ingest_result['updated']} updated, "
            f"{ingest_result['unchanged']} unchanged"
        )
    if args.update_snapshots:
        print(f"Updated variation price snapshots for {snapshots_updated} cards.")
    print("\n".join(rate_limit_lines))


if __name__ == "__main__":
    main()
