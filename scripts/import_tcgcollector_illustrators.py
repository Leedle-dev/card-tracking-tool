from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import argparse
import html
import re
import sqlite3
import time


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "card_tracker.sqlite"

REGION_ALIASES = {
    "english": "international",
    "international": "international",
    "intl": "international",
    "japanese": "japanese",
    "jp": "japanese",
    "s-chinese": "s-chinese",
    "simplified chinese": "s-chinese",
    "simplified-chinese": "s-chinese",
    "chinese": "s-chinese",
    "cn": "s-chinese",
}

ILLUSTRATORS_BLOCK_RE = re.compile(
    r'<div class="card-info-footer-item-title">\s*Illustrators\s*</div>\s*'
    r'<div class="card-info-footer-item-text-container">(?P<block>[\s\S]*?)'
    r'</div>\s*</div>',
    re.IGNORECASE,
)
ILLUSTRATOR_LINK_RE = re.compile(
    r'<a\s+href="(?P<href>[^"]+)"[^>]*>(?P<name>[\s\S]*?)</a>',
    re.IGNORECASE,
)
TAG_RE = re.compile(r"<[^>]+>")
WHITESPACE_RE = re.compile(r"\s+")


def normalize_region(language: str) -> str:
    key = language.strip().lower()
    if key not in REGION_ALIASES:
        valid = ", ".join(sorted(REGION_ALIASES))
        raise SystemExit(f"Unknown language/region '{language}'. Valid values: {valid}")
    return REGION_ALIASES[key]


def clean_text(value: str) -> str:
    value = TAG_RE.sub("", value)
    value = html.unescape(value)
    return WHITESPACE_RE.sub(" ", value).strip()


def fetch_url_text(url: str) -> str:
    request = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    try:
        with urlopen(request, timeout=30) as response:
            return response.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} for {url}\n{body[:500]}") from exc
    except URLError as exc:
        raise RuntimeError(f"Request failed for {url}: {exc}") from exc


def extract_illustrators(card_html: str) -> list[dict[str, str]]:
    block_match = ILLUSTRATORS_BLOCK_RE.search(card_html)
    if not block_match:
        return []

    illustrators = []
    seen_names = set()
    for match in ILLUSTRATOR_LINK_RE.finditer(block_match.group("block")):
        name = clean_text(match.group("name"))
        if not name:
            continue
        key = name.casefold()
        if key in seen_names:
            continue
        seen_names.add(key)
        illustrators.append({"name": name})
    return illustrators


def resolve_set(
    conn: sqlite3.Connection,
    region: str,
    set_name: str | None,
    set_code: str | None,
) -> dict[str, object]:
    clauses = ["source_region = ?"]
    params: list[object] = [region]
    if set_name:
        clauses.append("lower(set_name) = lower(?)")
        params.append(set_name)
    if set_code:
        clauses.append("set_code = ?")
        params.append(set_code)

    rows = conn.execute(
        f"""
        SELECT id, source_region, language, set_name, set_code, release_year
        FROM set_catalog
        WHERE {" AND ".join(clauses)}
        ORDER BY release_date_text DESC, id
        """,
        params,
    ).fetchall()

    if not rows and set_name:
        rows = conn.execute(
            """
            SELECT id, source_region, language, set_name, set_code, release_year
            FROM set_catalog
            WHERE source_region = ? AND lower(set_name) LIKE lower(?)
            ORDER BY release_date_text DESC, id
            """,
            (region, f"%{set_name}%"),
        ).fetchall()

    if not rows:
        raise SystemExit(
            "No set catalog match found. Provide --language with --set-name "
            "and/or --set-code, and refresh set_catalog if needed."
        )
    if len(rows) > 1:
        matches = "\n".join(
            f"- {row[2]} | {row[4] or 'NO-CODE'} | {row[3]}" for row in rows[:20]
        )
        raise SystemExit(f"Multiple set matches found. Be more specific:\n{matches}")

    row = rows[0]
    return {
        "id": row[0],
        "source_region": row[1],
        "language": row[2],
        "set_name": row[3],
        "set_code": row[4],
        "release_year": row[5],
    }


def cards_to_process(
    conn: sqlite3.Connection,
    set_catalog_id: int,
    limit: int | None,
    refresh: bool,
) -> list[sqlite3.Row]:
    skip_clause = "" if refresh else "AND ci.id IS NULL"
    limit_clause = "" if limit is None else "LIMIT ?"
    params: list[object] = [set_catalog_id]
    if limit is not None:
        params.append(limit)

    return conn.execute(
        f"""
        SELECT
            c.id,
            c.name,
            c.card_number,
            c.card_detail_url,
            COUNT(ci.id) AS illustrator_link_count
        FROM cards c
        LEFT JOIN card_illustrators ci ON ci.card_id = c.id
        WHERE
            c.set_catalog_id = ?
            AND c.card_detail_url IS NOT NULL
            AND c.card_detail_url <> ''
            {skip_clause}
        GROUP BY c.id
        ORDER BY c.card_number, c.tcgcollector_card_id
        {limit_clause}
        """,
        params,
    ).fetchall()


def illustrator_id(
    conn: sqlite3.Connection,
    name: str,
    release_year: int | None,
) -> int:
    row = conn.execute(
        "SELECT id FROM illustrators WHERE lower(name) = lower(?)",
        (name,),
    ).fetchone()
    if row:
        conn.execute(
            """
            UPDATE illustrators
            SET
                first_seen_year = CASE
                    WHEN ? IS NULL THEN first_seen_year
                    WHEN first_seen_year IS NULL THEN ?
                    WHEN first_seen_year > ? THEN ?
                    ELSE first_seen_year
                END,
                last_seen_year = CASE
                    WHEN ? IS NULL THEN last_seen_year
                    WHEN last_seen_year IS NULL THEN ?
                    WHEN last_seen_year < ? THEN ?
                    ELSE last_seen_year
                END
            WHERE id = ?
            """,
            (
                release_year,
                release_year,
                release_year,
                release_year,
                release_year,
                release_year,
                release_year,
                release_year,
                row["id"],
            ),
        )
        return int(row["id"])

    conn.execute(
        """
        INSERT INTO illustrators (
            name,
            first_seen_year,
            last_seen_year
        )
        VALUES (?, ?, ?)
        """,
        (name, release_year, release_year),
    )
    return int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])


def link_card_illustrator(
    conn: sqlite3.Connection,
    card_id: int,
    illustrator_id_value: int,
    source_url: str | None,
) -> None:
    conn.execute(
        """
        INSERT INTO card_illustrators (card_id, illustrator_id, source_url)
        VALUES (?, ?, ?)
        ON CONFLICT(card_id, illustrator_id) DO UPDATE SET
            source_url = COALESCE(card_illustrators.source_url, excluded.source_url)
        """,
        (card_id, illustrator_id_value, source_url),
    )


def import_illustrators(args: argparse.Namespace) -> None:
    region = normalize_region(args.language)
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        set_row = resolve_set(conn, region, args.set_name, args.set_code)
        cards = cards_to_process(conn, int(set_row["id"]), args.limit, args.refresh)

    print(
        f"Set: {set_row['language']} | {set_row.get('set_code') or 'NO-CODE'} | "
        f"{set_row['set_name']} | release year {set_row.get('release_year') or 'unknown'}"
    )
    print(f"Cards queued: {len(cards)}")

    fetched = 0
    linked = 0
    missing = 0
    failed = 0

    for index, card in enumerate(cards, start=1):
        try:
            card_html = fetch_url_text(card["card_detail_url"])
            illustrators = extract_illustrators(card_html)
        except RuntimeError as exc:
            failed += 1
            print(f"[{index}/{len(cards)}] ERROR {card['card_number']} {card['name']}: {exc}")
            continue

        fetched += 1
        if not illustrators:
            missing += 1
            print(f"[{index}/{len(cards)}] No illustrator found: {card['card_number']} {card['name']}")
            continue

        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            for illustrator in illustrators:
                artist_id = illustrator_id(
                    conn,
                    illustrator["name"],
                    set_row.get("release_year"),
                )
                link_card_illustrator(
                    conn,
                    int(card["id"]),
                    artist_id,
                    str(card["card_detail_url"]),
                )
                linked += 1

        names = ", ".join(illustrator["name"] for illustrator in illustrators)
        print(f"[{index}/{len(cards)}] {card['card_number']} {card['name']}: {names}")
        if args.delay_seconds > 0 and index < len(cards):
            time.sleep(args.delay_seconds)

    print()
    print(f"Fetched pages: {fetched}")
    print(f"Card-illustrator links written: {linked}")
    print(f"Cards missing illustrator block: {missing}")
    print(f"Failed pages: {failed}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import TCGcollector card illustrators for one local set."
    )
    # Argument examples:
    #   --language s-chinese --set-name "Gem Pack Vol. 5"
    #   --language japanese --set-code SV6a --limit 10
    #   --language english --set-name "Shrouded Fable" --refresh
    parser.add_argument("--language", default="s-chinese")
    parser.add_argument("--set-name", default="Gem Pack Vol. 5")
    parser.add_argument("--set-code", default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--delay-seconds", type=float, default=0.25)
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Fetch cards even when card_illustrators already has a link.",
    )
    args = parser.parse_args()

    if not DB_PATH.exists():
        raise SystemExit(f"Database not found: {DB_PATH}. Run scripts/init_db.py first.")

    import_illustrators(args)


if __name__ == "__main__":
    main()
