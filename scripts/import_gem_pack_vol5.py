from pathlib import Path
import hashlib
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
RELEASE_DATE = "2026-04-24"
RARITY_NOTE = "Includes Gem Rare, noted by PokiPair as exclusive to Simplified Chinese Pokemon."

POKEMON_NAMES = [
    "Captain Pikachu",
    "Hisuian Growlithe",
    "Magneton",
    "Chansey",
    "Horsea",
    "Sunflora",
    "Skarmory",
    "Houndoom",
    "Phanpy",
    "Vibrava",
    "Chimecho",
    "Spheal",
    "Latios",
    "Timburr",
    "Joltik",
    "Stunfisk",
    "Braviary",
    "Vivillon",
    "Raboot",
    "Applin",
    "Milcery",
    "Floragato",
    "Crocalor",
    "Quaxwell",
    "Ceruledge",
    "Wattrel",
    "Cetitan",
    "Tatsugiri",
]

VARIANTS = {
    "01": ("Common", "Energy Holo"),
    "02": ("Uncommon", "Poke Ball Holo"),
    "03": ("Uncommon", "Star Holo"),
    "04": ("Uncommon", "Windmill Holo"),
    "05": ("Rare", "Master Ball Holo"),
    "06": ("Double Rare", "Stamped Holo"),
    "07": ("Triple Rare", "Illustration Art Holo"),
}

IMAGE_RE = re.compile(
    r"https://media\.pokipair\.com/[^\" ]*"
    r"Gem-Pack-Vol-5-Simplified-Chinese-Pokemon-Set-List-PokiPair-Ireland-(\d{3})\.png"
)


def fetch_url_bytes(url: str) -> bytes:
    request = Request(
        url,
        headers={
            "User-Agent": "card-tracking-tool/0.1 (+local inventory research)"
        },
    )
    with urlopen(request, timeout=30) as response:
        return response.read()


def fetch_source_html() -> str:
    return fetch_url_bytes(SOURCE_URL).decode("utf-8", errors="replace")


def ensure_schema_columns(conn: sqlite3.Connection) -> None:
    card_columns = {
        row[1]
        for row in conn.execute("PRAGMA table_info(cards)").fetchall()
    }
    card_columns_to_add = {
        "pokemon_name": "TEXT",
        "pokemon_index": "INTEGER",
        "variant_code": "TEXT",
        "holo_pattern": "TEXT",
        "source_sequence": "INTEGER",
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


def extract_source_images(html: str) -> list[tuple[int, str]]:
    found = {}
    for match in IMAGE_RE.finditer(html):
        source_sequence = int(match.group(1))
        image_url = match.group(0)
        found[source_sequence] = image_url

    return sorted(found.items(), key=lambda item: item[0])


def build_card_identities() -> list[dict[str, object]]:
    identities = []
    for pokemon_index, pokemon_name in enumerate(POKEMON_NAMES, start=1):
        for variant_number in range(1, 8):
            variant_code = f"{variant_number:02d}"
            rarity, holo_pattern = VARIANTS[variant_code]
            set_number = f"{pokemon_index:02d}0{variant_number}"
            identities.append(
                {
                    "pokemon_name": pokemon_name,
                    "pokemon_index": pokemon_index,
                    "variant_code": variant_code,
                    "card_number": f"{set_number}/07",
                    "image_stem": f"{set_number}-07",
                    "rarity": rarity,
                    "holo_pattern": holo_pattern,
                }
            )
    return identities


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


def project_relative_path(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def download_unique_images(source_images: list[tuple[int, str]]) -> list[dict[str, object]]:
    downloaded = []
    seen_hashes: dict[str, int] = {}
    duplicate_sources = []

    for source_sequence, image_url in source_images:
        image_bytes = fetch_url_bytes(image_url)
        image_hash = hashlib.sha256(image_bytes).hexdigest()
        if image_hash in seen_hashes:
            duplicate_sources.append((source_sequence, seen_hashes[image_hash]))
            continue

        seen_hashes[image_hash] = source_sequence
        downloaded.append(
            {
                "source_sequence": source_sequence,
                "source_url": image_url,
                "image_hash": image_hash,
                "image_bytes": image_bytes,
            }
        )

    if duplicate_sources:
        duplicate_text = ", ".join(
            f"{duplicate} duplicates {original}"
            for duplicate, original in duplicate_sources
        )
        print(f"Skipped duplicate source images: {duplicate_text}")

    return downloaded


def insert_card(
    conn: sqlite3.Connection,
    identity: dict[str, object],
    image_record: dict[str, object],
) -> int:
    image_path = IMAGE_DIR / f"{identity['image_stem']}.png"
    image_path.write_bytes(image_record["image_bytes"])
    relative_image_path = project_relative_path(image_path)

    notes = (
        f"Seeded from PokiPair set list: {SOURCE_URL}\n"
        f"Release date: {RELEASE_DATE}\n"
        f"{RARITY_NOTE}\n"
        f"Source image sequence: {image_record['source_sequence']}"
    )

    conn.execute(
        """
        INSERT INTO cards (
            name,
            game,
            set_name,
            set_code,
            card_number,
            pokemon_name,
            pokemon_index,
            variant_code,
            rarity,
            holo_pattern,
            source_sequence,
            language,
            region,
            release_year,
            sale_status,
            notes,
            primary_image_path
        )
        VALUES (?, 'Pokemon', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'reference', ?, ?)
        """,
        (
            identity["pokemon_name"],
            SET_NAME,
            SET_CODE,
            identity["card_number"],
            identity["pokemon_name"],
            identity["pokemon_index"],
            identity["variant_code"],
            identity["rarity"],
            identity["holo_pattern"],
            image_record["source_sequence"],
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
        (SET_CODE, identity["card_number"], LANGUAGE),
    ).fetchone()[0]

    conn.execute(
        """
        INSERT INTO card_images (card_id, image_path, source_url, image_role, notes)
        VALUES (?, ?, ?, 'source_reference', ?)
        """,
        (
            card_id,
            relative_image_path,
            image_record["source_url"],
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
    source_images = extract_source_images(html)
    if not source_images:
        raise SystemExit("No Gem Pack Vol. 5 card images found in source page.")

    identities = build_card_identities()
    if len(identities) != 196:
        raise SystemExit(f"Expected 196 card identities, got {len(identities)}.")

    downloaded = download_unique_images(source_images)
    if len(downloaded) != len(identities):
        raise SystemExit(
            f"Expected {len(identities)} unique images, got {len(downloaded)}."
        )

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        ensure_schema_columns(conn)
        removed_rows = reset_existing_import(conn)
        removed_images = clear_existing_local_images()

        for identity, image_record in zip(identities, downloaded):
            insert_card(conn, identity, image_record)

    print(
        f"Rebuilt {len(identities)} {SET_NAME} card references in {DB_PATH}\n"
        f"Read {len(source_images)} source images and kept {len(downloaded)} unique images.\n"
        f"Deleted {removed_rows} old database rows and {removed_images} old local images.\n"
        f"Images saved to {IMAGE_DIR}"
    )


if __name__ == "__main__":
    main()
