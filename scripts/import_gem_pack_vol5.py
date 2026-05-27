from pathlib import Path
import re
import sqlite3
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "card_tracker.sqlite"
SOURCE_URL = "https://www.pokipair.com/gem-pack-vol-5-card-list/"
IMAGE_DIR = (
    ROOT
    / "data"
    / "card_images"
    / "s-chinese"
    / "2026-04-24-CBB5C-Gem-Pack-Vol-5"
)

SET_NAME = "Gem Pack Vol. 5"
SET_CODE = "CBB5C"
LANGUAGE = "Simplified Chinese"
REGION = "Mainland China"
RELEASE_YEAR = 2026
RARITY_NOTE = "Includes Gem Rare, noted by PokiPair as exclusive to Simplified Chinese Pokemon."

IMAGE_RE = re.compile(
    r"https://media\.pokipair\.com/[^\" ]*"
    r"Gem-Pack-Vol-5-Simplified-Chinese-Pokemon-Set-List-PokiPair-Ireland-(\d{3})\.png"
)


def fetch_source_html() -> str:
    request = Request(
        SOURCE_URL,
        headers={
            "User-Agent": "card-tracking-tool/0.1 (+local inventory research)"
        },
    )
    with urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


def ensure_source_url_column(conn: sqlite3.Connection) -> None:
    columns = {
        row[1]
        for row in conn.execute("PRAGMA table_info(card_images)").fetchall()
    }
    if "source_url" not in columns:
        conn.execute("ALTER TABLE card_images ADD COLUMN source_url TEXT")


def extract_cards(html: str) -> list[tuple[str, str]]:
    found = {}
    for match in IMAGE_RE.finditer(html):
        card_number = match.group(1)
        image_url = match.group(0)
        found[card_number] = image_url

    return sorted(found.items(), key=lambda item: item[0])


def reset_existing_import(conn: sqlite3.Connection) -> int:
    card_ids = [
        row[0]
        for row in conn.execute(
            """
            SELECT id
            FROM cards
            WHERE set_code = ? AND language = ?
            """,
            (SET_CODE, LANGUAGE),
        ).fetchall()
    ]
    conn.execute(
        """
        DELETE FROM cards
        WHERE set_code = ? AND language = ?
        """,
        (SET_CODE, LANGUAGE),
    )
    return len(card_ids)


def clear_existing_local_images() -> int:
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    removed = 0
    for path in IMAGE_DIR.glob("*.png"):
        path.unlink()
        removed += 1
    return removed


def download_image(card_number: str, image_url: str) -> Path:
    image_path = IMAGE_DIR / f"{card_number}.png"
    request = Request(
        image_url,
        headers={
            "User-Agent": "card-tracking-tool/0.1 (+local inventory research)"
        },
    )
    with urlopen(request, timeout=30) as response:
        image_path.write_bytes(response.read())
    return image_path


def project_relative_path(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def insert_card(
    conn: sqlite3.Connection,
    card_number: str,
    source_url: str,
    local_image_path: Path,
) -> int:
    display_name = f"{SET_NAME} #{card_number}"
    relative_image_path = project_relative_path(local_image_path)
    notes = (
        f"Seeded from PokiPair set list: {SOURCE_URL}\n"
        f"{RARITY_NOTE}\n"
        "Placeholder name until the card identity is manually confirmed or OCR is added."
    )

    conn.execute(
        """
        INSERT INTO cards (
            name,
            game,
            set_name,
            set_code,
            card_number,
            language,
            region,
            release_year,
            sale_status,
            notes,
            primary_image_path
        )
        VALUES (?, 'Pokemon', ?, ?, ?, ?, ?, ?, 'reference', ?, ?)
        """,
        (
            display_name,
            SET_NAME,
            SET_CODE,
            card_number,
            LANGUAGE,
            REGION,
            RELEASE_YEAR,
            notes,
            relative_image_path,
        ),
    )

    card_id = conn.execute(
        """
        SELECT id
        FROM cards
        WHERE set_code = ? AND card_number = ? AND language = ?
        """,
        (SET_CODE, card_number, LANGUAGE),
    ).fetchone()[0]

    conn.execute(
        """
        INSERT INTO card_images (card_id, image_path, source_url, image_role, notes)
        VALUES (?, ?, ?, 'source_reference', ?)
        """,
        (
            card_id,
            relative_image_path,
            source_url,
            f"Downloaded from PokiPair set list: {SOURCE_URL}",
        ),
    )

    return card_id


def main() -> None:
    if not DB_PATH.exists():
        raise SystemExit(
            f"Database not found: {DB_PATH}. Run scripts/init_db.py first."
        )

    html = fetch_source_html()
    cards = extract_cards(html)
    if not cards:
        raise SystemExit("No Gem Pack Vol. 5 card images found in source page.")

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        ensure_source_url_column(conn)
        removed_rows = reset_existing_import(conn)

    removed_images = clear_existing_local_images()
    downloaded = []
    for card_number, image_url in cards:
        downloaded.append((card_number, image_url, download_image(card_number, image_url)))

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        ensure_source_url_column(conn)
        for card_number, image_url, local_image_path in downloaded:
            insert_card(conn, card_number, image_url, local_image_path)

    print(
        f"Rebuilt {len(cards)} {SET_NAME} card references in {DB_PATH}\n"
        f"Deleted {removed_rows} old database rows and {removed_images} old local images.\n"
        f"Images saved to {IMAGE_DIR}"
    )


if __name__ == "__main__":
    main()
