from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen
import argparse
import html
import re
import shutil
import sqlite3
import unicodedata


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "card_tracker.sqlite"
BASE_URL = "https://www.tcgcollector.com"

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

LANGUAGE_BY_REGION = {
    "international": "English",
    "japanese": "Japanese",
    "s-chinese": "Simplified Chinese",
}

CARD_TILE_RE = re.compile(
    r'<div\s+class="(?=[^"]*card-image-grid-item)[^"]*"'
    r'[\s\S]*?data-card-id="(?P<card_id>\d+)"'
    r'[\s\S]*?</a>',
    re.MULTILINE,
)
CARD_NAME_RE = re.compile(r'title="(?P<full_name>[^"]+)"')
CARD_DETAIL_RE = re.compile(r'href="(?P<detail_path>/cards/\d+/[^"]+)"')
CARD_SLUG_RE = re.compile(r'href="/cards/\d+/(?P<slug>[^"]+)"')
CARD_IMAGE_RE = re.compile(
    r'<img[\s\S]*?src="(?P<src>[^"]+)"[\s\S]*?'
    r'class="card-image-grid-item-image"'
)
CARD_IMAGE_SRCSET_RE = re.compile(
    r'<img[\s\S]*?srcset="(?P<srcset>[^"]+)"[\s\S]*?'
    r'class="card-image-grid-item-image"'
)
CARD_NUMBER_RE = re.compile(
    r'<div class="card-image-grid-item-info-overlay-number">\s*'
    r'(?P<card_number>[^<]+?)\s*</div>'
)
RARITY_RE = re.compile(
    r'alt="(?P<rarity>[^"]+)"[^>]+'
    r'class="card-rarity-symbol card-image-grid-item-info-overlay-rarity-symbol"'
)


def normalize_region(language: str) -> str:
    key = language.strip().lower()
    if key not in REGION_ALIASES:
        valid = ", ".join(sorted(REGION_ALIASES))
        raise SystemExit(f"Unknown language/region '{language}'. Valid values: {valid}")
    return REGION_ALIASES[key]


def slugify(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.strip())
    value = value.encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^A-Za-z0-9]+", "-", value.strip())
    return value.strip("-") or "unknown"


def release_date_slug(release_date_text: str | None) -> str:
    if not release_date_text:
        return "unknown-date"
    try:
        return datetime.strptime(release_date_text, "%b %d, %Y").strftime("%Y-%m-%d")
    except ValueError:
        return slugify(release_date_text).lower()


def image_extension(url: str) -> str:
    suffix = Path(urlparse(url).path).suffix.lower()
    return suffix if suffix else ".webp"


def fetch_url_bytes(url: str) -> bytes:
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
            return response.read()
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"Request failed for {url}: HTTP {exc.code}\n{body[:500]}") from exc
    except URLError as exc:
        raise SystemExit(f"Request failed for {url}: {exc}") from exc


def ensure_schema_columns(conn: sqlite3.Connection) -> None:
    card_columns = {
        row[1]
        for row in conn.execute("PRAGMA table_info(cards)").fetchall()
    }
    card_columns_to_add = {
        "set_catalog_id": "INTEGER",
        "pokedex_id": "INTEGER",
        "pokemon_name": "TEXT",
        "holo_pattern": "TEXT",
        "source_sequence": "INTEGER",
        "tcgcollector_card_id": "INTEGER",
        "card_detail_url": "TEXT",
    }
    for column, column_type in card_columns_to_add.items():
        if column not in card_columns:
            conn.execute(f"ALTER TABLE cards ADD COLUMN {column} {column_type}")

    image_columns = {
        row[1]
        for row in conn.execute("PRAGMA table_info(card_images)").fetchall()
    }
    if "source_url" not in image_columns:
        conn.execute("ALTER TABLE card_images ADD COLUMN source_url TEXT")

    set_catalog_columns = {
        row[1]
        for row in conn.execute("PRAGMA table_info(set_catalog)").fetchall()
    }
    set_catalog_columns_to_add = {
        "language": "TEXT",
        "release_year": "INTEGER",
    }
    for column, column_type in set_catalog_columns_to_add.items():
        if column not in set_catalog_columns:
            conn.execute(f"ALTER TABLE set_catalog ADD COLUMN {column} {column_type}")


def resolve_set(conn: sqlite3.Connection, region: str, set_name: str) -> dict[str, object]:
    exact_rows = conn.execute(
        """
        SELECT
            id,
            source_region,
            language,
            tcgcollector_set_id,
            set_name,
            set_code,
            release_date_text,
            release_year,
            card_count,
            set_url,
            slug
        FROM set_catalog
        WHERE source_region = ? AND lower(set_name) = lower(?)
        ORDER BY release_date_text DESC
        """,
        (region, set_name),
    ).fetchall()
    rows = exact_rows
    if not rows:
        rows = conn.execute(
            """
            SELECT
                id,
                source_region,
                language,
                tcgcollector_set_id,
                set_name,
                set_code,
                release_date_text,
                release_year,
                card_count,
                set_url,
                slug
            FROM set_catalog
            WHERE source_region = ? AND lower(set_name) LIKE lower(?)
            ORDER BY release_date_text DESC
            """,
            (region, f"%{set_name}%"),
        ).fetchall()

    if not rows:
        raise SystemExit(
            f"No set catalog match for region '{region}' and set name '{set_name}'. "
            "Run scripts/fetch_tcgcollector_sets.py and "
            "scripts/import_tcgcollector_set_catalog.py if the catalog is stale."
        )
    if len(rows) > 1 and not exact_rows:
        matches = "\n".join(f"- {row[2]} ({row[3]})" for row in rows[:20])
        raise SystemExit(
            f"Multiple set matches for '{set_name}'. Use a more exact name:\n{matches}"
        )

    row = rows[0]
    return {
        "id": row[0],
        "source_region": row[1],
        "language": row[2],
        "tcgcollector_set_id": row[3],
        "set_name": row[4],
        "set_code": row[5],
        "release_date_text": row[6],
        "release_year": row[7],
        "card_count": row[8],
        "set_url": row[9],
        "slug": row[10],
    }


def best_srcset_url(srcset: str) -> str:
    candidates = []
    for item in srcset.split(","):
        parts = item.strip().split()
        if not parts:
            continue
        url = parts[0]
        width = 0
        if len(parts) > 1 and parts[1].endswith("w"):
            try:
                width = int(parts[1][:-1])
            except ValueError:
                width = 0
        candidates.append((width, url))
    if not candidates:
        return ""
    return max(candidates, key=lambda candidate: candidate[0])[1]


def extract_cards(set_html: str) -> list[dict[str, object]]:
    cards_by_id = {}
    for index, match in enumerate(CARD_TILE_RE.finditer(set_html), start=1):
        card_html = match.group(0)
        name_match = CARD_NAME_RE.search(card_html)
        detail_match = CARD_DETAIL_RE.search(card_html)
        slug_match = CARD_SLUG_RE.search(card_html)
        image_match = CARD_IMAGE_RE.search(card_html)
        srcset_match = CARD_IMAGE_SRCSET_RE.search(card_html)
        number_match = CARD_NUMBER_RE.search(card_html)
        rarity_match = RARITY_RE.search(card_html)
        if not name_match or not detail_match or not image_match or not number_match:
            continue

        image_url = ""
        if srcset_match:
            image_url = best_srcset_url(html.unescape(srcset_match.group("srcset")))
        if not image_url:
            image_url = html.unescape(image_match.group("src"))

        full_name = html.unescape(name_match.group("full_name")).strip()
        card_id = int(match.group("card_id"))
        cards_by_id[card_id] = {
            "source_sequence": index,
            "tcgcollector_card_id": card_id,
            "name": full_name.split(" (", 1)[0],
            "card_number": html.unescape(number_match.group("card_number")).strip(),
            "rarity": html.unescape(rarity_match.group("rarity")).strip() if rarity_match else None,
            "full_name": full_name,
            "slug": slug_match.group("slug") if slug_match else "",
            "card_detail_url": urljoin(BASE_URL, detail_match.group("detail_path")),
            "source_image_url": image_url,
        }

    return sorted(
        cards_by_id.values(),
        key=lambda card: (str(card["card_number"]), int(card["tcgcollector_card_id"])),
    )


def image_dir_for_set(set_row: dict[str, object], region: str) -> Path:
    date_part = release_date_slug(set_row.get("release_date_text"))
    code_part = slugify(str(set_row.get("set_code") or "NO-CODE"))
    name_part = slugify(str(set_row["set_name"]))
    return ROOT / "data" / "card_images" / region / f"{date_part}-{code_part}-{name_part}"


def clear_existing_local_images(image_dir: Path) -> int:
    if not image_dir.exists():
        image_dir.mkdir(parents=True, exist_ok=True)
        return 0

    removed = 0
    for path in image_dir.iterdir():
        if path.name == ".gitkeep":
            continue
        if path.is_file():
            path.unlink()
            removed += 1
        elif path.is_dir():
            shutil.rmtree(path)
            removed += 1
    return removed


def reset_existing_import(
    conn: sqlite3.Connection,
    set_catalog_id: int | None,
) -> int:
    rows = conn.execute(
        """
        SELECT id
        FROM cards
        WHERE set_catalog_id = ?
        """,
        (set_catalog_id,),
    ).fetchall()
    conn.execute(
        """
        DELETE FROM cards
        WHERE set_catalog_id = ?
        """,
        (set_catalog_id,),
    )
    return len(rows)


def project_relative_path(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def import_card(
    conn: sqlite3.Connection,
    set_row: dict[str, object],
    card: dict[str, object],
    image_dir: Path,
) -> None:
    source_image_url = str(card["source_image_url"])
    image_bytes = fetch_url_bytes(source_image_url)
    image_filename = f"{slugify(str(card['card_number']).replace('/', '-'))}{image_extension(source_image_url)}"
    image_path = image_dir / image_filename
    image_path.write_bytes(image_bytes)
    relative_image_path = project_relative_path(image_path)

    notes = (
        f"Imported from TCGcollector set page: {set_row['set_url']}\n"
        f"TCGcollector card page: {card['card_detail_url']}"
    )

    conn.execute(
        """
        INSERT INTO cards (
            set_catalog_id,
            name,
            game,
            card_number,
            pokemon_name,
            rarity,
            source_sequence,
            tcgcollector_card_id,
            card_detail_url,
            notes,
            primary_image_path
        )
        VALUES (?, ?, 'Pokemon', ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            set_row["id"],
            card["name"],
            card["card_number"],
            card["name"],
            card.get("rarity"),
            card["source_sequence"],
            card["tcgcollector_card_id"],
            card["card_detail_url"],
            notes,
            relative_image_path,
        ),
    )

    card_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    conn.execute(
        """
        INSERT INTO card_inventory (card_id, sale_status)
        VALUES (?, 'reference')
        ON CONFLICT(card_id) DO UPDATE SET
            sale_status = excluded.sale_status
        """,
        (card_id,),
    )

    conn.execute(
        """
        INSERT INTO card_images (card_id, image_path, source_url, image_role, notes)
        VALUES (?, ?, ?, 'tcgcollector_card_image', ?)
        """,
        (
            card_id,
            relative_image_path,
            source_image_url,
            f"Downloaded from {card['card_detail_url']}",
        ),
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Import a Pokemon card set from TCGcollector using a language/region "
            "and set name resolved from the local set_catalog table."
        )
    )
    parser.add_argument("--language", default="s-chinese")
    parser.add_argument("--set-name", default="Gem Pack Vol. 5")
    args = parser.parse_args()

    if not DB_PATH.exists():
        raise SystemExit(f"Database not found: {DB_PATH}. Run scripts/init_db.py first.")

    region = normalize_region(args.language)
    language = LANGUAGE_BY_REGION[region]

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        ensure_schema_columns(conn)
        set_row = resolve_set(conn, region, args.set_name)

    set_html = fetch_url_bytes(str(set_row["set_url"])).decode("utf-8", errors="replace")
    cards = extract_cards(set_html)
    if not cards:
        raise SystemExit(f"No cards parsed from {set_row['set_url']}")

    expected_count = set_row.get("card_count")
    if expected_count and len(cards) != expected_count:
        print(f"Warning: catalog count is {expected_count}, parsed {len(cards)} cards.")

    image_dir = image_dir_for_set(set_row, region)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        ensure_schema_columns(conn)
        removed_rows = reset_existing_import(
            conn,
            int(set_row["id"]),
        )
        removed_images = clear_existing_local_images(image_dir)

        for card in cards:
            import_card(conn, set_row, card, image_dir)

    print(
        f"Imported {len(cards)} cards for {language} {set_row['set_name']} "
        f"({set_row.get('set_code')}) into {DB_PATH}\n"
        f"Deleted {removed_rows} old database rows and {removed_images} old local image files.\n"
        f"Images saved to {image_dir}"
    )


if __name__ == "__main__":
    main()
