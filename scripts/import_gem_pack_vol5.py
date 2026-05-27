from pathlib import Path
import re
import sqlite3
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "card_tracker.sqlite"
SOURCE_URL = "https://www.pokipair.com/gem-pack-vol-5-card-list/"

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


def extract_cards(html: str) -> list[tuple[str, str]]:
    found = {}
    for match in IMAGE_RE.finditer(html):
        card_number = match.group(1)
        image_url = match.group(0)
        found[card_number] = image_url

    return sorted(found.items(), key=lambda item: item[0])


def upsert_card(conn: sqlite3.Connection, card_number: str, image_url: str) -> int:
    display_name = f"{SET_NAME} #{card_number}"
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
        ON CONFLICT(set_code, card_number, language) DO UPDATE SET
            name = excluded.name,
            set_name = excluded.set_name,
            region = excluded.region,
            release_year = excluded.release_year,
            notes = excluded.notes,
            primary_image_path = excluded.primary_image_path
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
            image_url,
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
        INSERT INTO card_images (card_id, image_path, image_role, notes)
        VALUES (?, ?, 'source_reference', ?)
        ON CONFLICT(card_id, image_path, image_role) DO UPDATE SET
            notes = excluded.notes
        """,
        (card_id, image_url, f"Image reference from {SOURCE_URL}"),
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
        for card_number, image_url in cards:
            upsert_card(conn, card_number, image_url)

    print(f"Imported {len(cards)} {SET_NAME} card references into {DB_PATH}")


if __name__ == "__main__":
    main()
