from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import argparse
import csv
import json
import re
import sys

from sqlalchemy import func, select


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from card_tracker.db import session_scope
from card_tracker.db.models import Card, SetCatalog
from fetch_houndoom_browse import (
    FILTERED_TSV_COLUMNS,
    TSV_COLUMNS,
    app_access_token,
    browse_search,
    fetch_rate_limits,
    filter_reasons,
    filter_warnings,
    flatten_item,
    format_rate_limit_lines,
    search_query_text,
)


OUTPUT_DIR = SCRIPT_DIR / "output"
DEFAULT_LIMIT = 200
VARIATION_TSV_COLUMNS = [*FILTERED_TSV_COLUMNS, "first_seen_query_label"]


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return slug or "unknown"


def language_key(language: str | None, source_region: str | None) -> str:
    value = (language or source_region or "").lower()
    if value in {"s-chinese", "simplified chinese", "cn", "china"}:
        return "s-chinese"
    if value in {"japanese", "jp", "japan"}:
        return "japanese"
    if value in {"english", "intl", "international"}:
        return "english"
    return value or "unknown"


def build_query(card: Card, set_catalog: SetCatalog, limit: int) -> dict[str, object]:
    pokemon_name = card.pokemon_name or card.name
    language = language_key(set_catalog.language, set_catalog.source_region)
    label_parts = [
        str(card.id),
        language,
        pokemon_name,
        card.card_number or "unknown_number",
        set_catalog.set_code or "unknown_set_code",
    ]

    return {
        "label": slugify("_".join(label_parts)),
        "card_id": card.id,
        "set_catalog_id": set_catalog.id,
        "language": language,
        "pokemon_name": pokemon_name,
        "card_number": card.card_number or "",
        "set_code": set_catalog.set_code or "",
        "set_name": set_catalog.set_name,
        "limit": limit,
    }


def load_card_queries(set_code: str, set_name: str, limit: int, db_path: Path) -> list[dict[str, object]]:
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch eBay Browse API listing summaries for every card in a local set."
    )
    # Example:
    #   python modeling/ebay_browse/fetch_ebay_listings.py --set-code CBB5C --set-name "Gem Pack Vol. 5"
    parser.add_argument("--set-code", required=True, help="Set code from set_catalog, such as CBB5C.")
    parser.add_argument("--set-name", required=True, help='Set name from set_catalog, such as "Gem Pack Vol. 5".')
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="eBay Browse results per card query.")
    parser.add_argument(
        "--db-path",
        type=Path,
        default=ROOT / "data" / "card_tracker.sqlite",
        help="Path to the local SQLite database.",
    )
    parser.add_argument(
        "--max-cards",
        type=int,
        help="Optional safety cap for testing, such as --max-cards 5.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print generated queries without calling eBay.",
    )
    parser.add_argument(
        "--ingest",
        action="store_true",
        help="Ingest the completed fetch run into SQLite after writing TSV files.",
    )
    return parser.parse_args()


def write_tsv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def is_variation_row(row: dict[str, str]) -> bool:
    return row.get("is_variation_listing") == "True" or bool(row.get("item_group_href"))


def main() -> None:
    args = parse_args()
    if args.limit < 1 or args.limit > 200:
        raise SystemExit("--limit must be between 1 and 200.")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_label = slugify(f"{args.set_code}_{args.set_name}")

    queries = load_card_queries(args.set_code, args.set_name, args.limit, args.db_path)
    if args.max_cards is not None:
        queries = queries[: args.max_cards]

    if not queries:
        raise SystemExit(f"No cards found for set_code={args.set_code!r} and set_name={args.set_name!r}.")

    if args.dry_run:
        for query in queries:
            print(json.dumps({**query, "query": search_query_text(query)}, sort_keys=True))
        print(f"Generated {len(queries)} eBay queries.")
        return

    run_dir = OUTPUT_DIR / f"{timestamp}_{output_label}"
    raw_dir = run_dir / "raw"
    run_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)

    access_token = app_access_token()
    rows = []
    accepted_rows = []
    rejected_rows = []
    variation_rows = []
    seen_variation_item_ids = set()
    browse_call_count = 0
    query_metadata = []
    summary_lines = [
        "eBay Browse API set listing search",
        f"Fetched at UTC: {timestamp}",
        f"Set code: {args.set_code}",
        f"Set name: {args.set_name}",
        f"Card queries: {len(queries)}",
        f"Results per query: {args.limit}",
        "",
    ]

    for query in queries:
        payload = browse_search(access_token, query)
        browse_call_count += 1
        raw_path = raw_dir / f"{timestamp}_{query['label']}.json"
        raw_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

        items = payload.get("itemSummaries", [])
        if not isinstance(items, list):
            items = []
        result_count = int(payload.get("total", len(items)) or 0)
        query_accepted = 0
        query_rejected = 0
        query_variations = 0
        for item in items:
            if isinstance(item, dict):
                row = flatten_item(query, result_count, item)
                reasons = filter_reasons(query, row)
                warnings = filter_warnings(query, row)
                filtered_row = {
                    **row,
                    "filter_reasons": ";".join(reasons),
                    "filter_warnings": ";".join(warnings),
                }
                if is_variation_row(row):
                    query_variations += 1
                    item_id = row["item_id"]
                    if item_id not in seen_variation_item_ids:
                        seen_variation_item_ids.add(item_id)
                        variation_rows.append({**filtered_row, "first_seen_query_label": str(query["label"])})
                    continue

                rows.append(row)
                if reasons:
                    rejected_rows.append(filtered_row)
                    query_rejected += 1
                else:
                    accepted_rows.append(filtered_row)
                    query_accepted += 1
        summary_lines.append(
            f"{query['label']}: total={result_count}, exported={len(items)}, "
            f"accepted={query_accepted}, rejected={query_rejected}, variations={query_variations}"
        )
        query_metadata.append(
            {
                **query,
                "query_text": search_query_text(query),
                "result_total": result_count,
                "result_exported": len(items),
                "accepted_count": query_accepted,
                "rejected_count": query_rejected,
                "variation_count": query_variations,
                "raw_json_path": str(raw_path),
            }
        )

    summary_lines.extend(
        [
            "",
            f"Browse search API calls this run: {browse_call_count}",
            "Rate-limit API calls this run: 1",
        ]
    )

    tsv_path = run_dir / f"{timestamp}_{output_label}_ebay_listings.tsv"
    filtered_tsv_path = run_dir / f"{timestamp}_{output_label}_ebay_listings_filtered.tsv"
    rejected_tsv_path = run_dir / f"{timestamp}_{output_label}_ebay_listings_rejected.tsv"
    variations_tsv_path = run_dir / f"{timestamp}_{output_label}_ebay_listings_variations.tsv"
    metadata_path = run_dir / f"{timestamp}_{output_label}_ebay_listings_metadata.json"
    write_tsv(tsv_path, TSV_COLUMNS, rows)
    write_tsv(filtered_tsv_path, FILTERED_TSV_COLUMNS, accepted_rows)
    write_tsv(rejected_tsv_path, FILTERED_TSV_COLUMNS, rejected_rows)
    write_tsv(variations_tsv_path, VARIATION_TSV_COLUMNS, variation_rows)

    rate_limit_payload, rate_limit_error = fetch_rate_limits(access_token)
    rate_limit_lines = format_rate_limit_lines(rate_limit_payload, rate_limit_error)
    summary_lines.extend(rate_limit_lines)

    rate_limit_path = raw_dir / f"{timestamp}_{output_label}_ebay_rate_limits.json"
    if rate_limit_payload is not None:
        rate_limit_path.write_text(json.dumps(rate_limit_payload, indent=2, sort_keys=True), encoding="utf-8")

    summary_path = run_dir / f"{timestamp}_{output_label}_ebay_listings_summary.txt"
    summary_path.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")
    metadata = {
        "timestamp": timestamp,
        "set_code": args.set_code,
        "set_name": args.set_name,
        "set_catalog_id": queries[0].get("set_catalog_id"),
        "query_limit": args.limit,
        "query_count": len(queries),
        "browse_call_count": browse_call_count,
        "output_dir": str(run_dir),
        "files": {
            "all": str(tsv_path),
            "filtered": str(filtered_tsv_path),
            "rejected": str(rejected_tsv_path),
            "variations": str(variations_tsv_path),
            "summary": str(summary_path),
            "rate_limits": str(rate_limit_path),
        },
        "queries": query_metadata,
    }
    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")

    print(f"Wrote {len(rows)} rows to {tsv_path}")
    print(f"Wrote {len(accepted_rows)} accepted rows to {filtered_tsv_path}")
    print(f"Wrote {len(rejected_rows)} rejected rows to {rejected_tsv_path}")
    print(f"Wrote {len(variation_rows)} unique variation rows to {variations_tsv_path}")
    print(f"Wrote summary to {summary_path}")
    print(f"Wrote metadata to {metadata_path}")
    print(f"Wrote raw JSON files to {raw_dir}")
    for line in rate_limit_lines:
        print(line)

    if args.ingest:
        from ingest_ebay_listings import ingest_run

        result = ingest_run(run_dir=run_dir, db_path=args.db_path)
        print(
            "Ingested run "
            f"{result['fetch_run_id']}: "
            f"{result['listings']} listings, "
            f"{result['listings_created']} created, "
            f"{result['listings_updated']} updated, "
            f"{result['listings_unchanged']} unchanged, "
            f"{result['matches']} matches, "
            f"{result['price_snapshots']} price snapshots"
        )


if __name__ == "__main__":
    main()
