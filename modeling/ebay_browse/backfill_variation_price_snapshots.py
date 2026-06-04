from __future__ import annotations

from pathlib import Path
import argparse
import sqlite3
import statistics
import sys


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ingest_ebay_listings import percentile, trimmed_mean


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill variation listing price snapshots from existing eBay variation matches."
    )
    # Argument examples:
    #   python modeling/ebay_browse/backfill_variation_price_snapshots.py
    #   python modeling/ebay_browse/backfill_variation_price_snapshots.py --fetch-run-id 2
    #   python modeling/ebay_browse/backfill_variation_price_snapshots.py --fetch-run-id 2 --replace
    parser.add_argument(
        "--db-path",
        type=Path,
        default=ROOT / "data" / "card_tracker.sqlite",
        help="Path to the local SQLite database.",
    )
    parser.add_argument("--fetch-run-id", type=int, help="Optional fetch run to backfill.")
    parser.add_argument("--replace", action="store_true", help="Replace existing variation snapshots.")
    return parser.parse_args()


def fetch_run_cards(conn: sqlite3.Connection, fetch_run_id: int | None) -> list[tuple[int, int]]:
    params: list[int] = []
    run_filter = ""
    if fetch_run_id is not None:
        run_filter = "AND ml.fetch_run_id = ?"
        params.append(fetch_run_id)

    return conn.execute(
        f"""
        SELECT DISTINCT ml.fetch_run_id, mlm.card_id
        FROM marketplace_listing_matches mlm
        JOIN marketplace_listings ml ON ml.id = mlm.listing_id
        WHERE mlm.match_status = 'variation'
            {run_filter}
        ORDER BY ml.fetch_run_id, mlm.card_id
        """,
        params,
    ).fetchall()


def fetch_variation_listings(conn: sqlite3.Connection, fetch_run_id: int, card_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT DISTINCT
            ml.id,
            ml.price_cents,
            ml.item_location_country
        FROM marketplace_listing_matches mlm
        JOIN marketplace_listings ml ON ml.id = mlm.listing_id
        WHERE mlm.match_status = 'variation'
            AND ml.fetch_run_id = ?
            AND mlm.card_id = ?
        """,
        (fetch_run_id, card_id),
    ).fetchall()


def build_snapshot(fetch_run_id: int, card_id: int, rows: list[sqlite3.Row]) -> tuple[object, ...]:
    prices = [row["price_cents"] for row in rows if row["price_cents"] is not None]
    domestic_count = sum(1 for row in rows if row["item_location_country"] == "US")
    international_count = sum(
        1 for row in rows if row["item_location_country"] and row["item_location_country"] != "US"
    )
    p25 = percentile(prices, 0.25)
    p75 = percentile(prices, 0.75)

    return (
        fetch_run_id,
        card_id,
        len(rows),
        min(prices) if prices else None,
        max(prices) if prices else None,
        float(statistics.mean(prices)) if prices else None,
        float(statistics.median(prices)) if prices else None,
        float(statistics.stdev(prices)) if len(prices) > 1 else 0.0 if prices else None,
        percentile(prices, 0.10),
        p25,
        p75,
        percentile(prices, 0.90),
        (p75 - p25) if p25 is not None and p75 is not None else None,
        trimmed_mean(prices),
        domestic_count,
        international_count,
    )


def main() -> None:
    args = parse_args()
    with sqlite3.connect(args.db_path) as conn:
        conn.row_factory = sqlite3.Row
        run_cards = fetch_run_cards(conn, args.fetch_run_id)
        inserted = 0
        replaced = 0
        skipped = 0

        with conn:
            for fetch_run_id, card_id in run_cards:
                existing = conn.execute(
                    """
                    SELECT 1
                    FROM marketplace_variation_price_snapshots
                    WHERE fetch_run_id = ?
                        AND card_id = ?
                    """,
                    (fetch_run_id, card_id),
                ).fetchone()

                if existing and not args.replace:
                    skipped += 1
                    continue

                if existing:
                    conn.execute(
                        """
                        DELETE FROM marketplace_variation_price_snapshots
                        WHERE fetch_run_id = ?
                            AND card_id = ?
                        """,
                        (fetch_run_id, card_id),
                    )
                    replaced += 1

                rows = fetch_variation_listings(conn, fetch_run_id, card_id)
                conn.execute(
                    """
                    INSERT INTO marketplace_variation_price_snapshots (
                        fetch_run_id,
                        card_id,
                        variation_listing_count,
                        min_price_cents,
                        max_price_cents,
                        mean_price_cents,
                        median_price_cents,
                        stddev_price_cents,
                        p10_price_cents,
                        p25_price_cents,
                        p75_price_cents,
                        p90_price_cents,
                        iqr_price_cents,
                        trimmed_mean_price_cents,
                        domestic_listing_count,
                        international_listing_count
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    build_snapshot(fetch_run_id, card_id, rows),
                )
                inserted += 1

    print(f"Variation snapshot cards found: {len(run_cards)}")
    print(f"Inserted: {inserted}")
    print(f"Replaced: {replaced}")
    print(f"Skipped existing: {skipped}")


if __name__ == "__main__":
    main()
