from __future__ import annotations

from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import argparse
import json
import re
import sqlite3
import unicodedata


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "card_tracker.sqlite"
BASE_URL = "https://pokeapi.co/api/v2"

REGIONAL_VARIANTS = {
    "alola": "Alolan",
    "galar": "Galarian",
    "hisui": "Hisuian",
    "paldea": "Paldean",
}

CARD_NAME_PREFIX_VARIANTS = {
    "Alolan": "Alolan",
    "Galarian": "Galarian",
    "Hisuian": "Hisuian",
    "Paldean": "Paldean",
}

CARD_NAME_PREFIXES_TO_IGNORE = [
    "Captain ",
]

CARD_NAME_SUFFIX_RE = re.compile(
    r"\s+("
    r"ex|EX|V|VMAX|VSTAR|GX|BREAK|Radiant|Prism Star|Star|LV\.?\s*X"
    r")$",
    re.IGNORECASE,
)


def fetch_json(url: str) -> dict[str, object]:
    request = Request(
        url,
        headers={
            "User-Agent": "Card Tracking Tool local importer",
            "Accept": "application/json",
        },
    )
    try:
        with urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise SystemExit(f"Request failed for {url}: HTTP {exc.code}") from exc
    except URLError as exc:
        raise SystemExit(f"Request failed for {url}: {exc}") from exc


def english_name(species: dict[str, object]) -> str:
    for name_row in species.get("names", []):
        language = name_row.get("language", {})
        if language.get("name") == "en":
            return str(name_row["name"])
    return str(species["name"]).replace("-", " ").title()


def variant_from_slug(slug: str) -> str | None:
    parts = set(slug.split("-"))
    for marker, variant_name in REGIONAL_VARIANTS.items():
        if marker in parts:
            return variant_name
    return None


def normalize_card_name(card_name: str) -> tuple[str, str | None]:
    name = card_name.strip()
    name = re.sub(r"\s*\([^)]*\)\s*", " ", name).strip()
    for prefix in CARD_NAME_PREFIXES_TO_IGNORE:
        if name.startswith(prefix):
            name = name[len(prefix):].strip()

    variant_name = None
    for prefix, variant in CARD_NAME_PREFIX_VARIANTS.items():
        prefix_text = f"{prefix} "
        if name.startswith(prefix_text):
            variant_name = variant
            name = name[len(prefix_text):].strip()
            break

    previous = None
    while previous != name:
        previous = name
        name = CARD_NAME_SUFFIX_RE.sub("", name).strip()

    return name, variant_name


def lookup_key(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = value.replace("♀", "f").replace("♂", "m")
    value = value.replace("'", "").replace("’", "")
    value = value.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def load_pokedex_rows() -> list[dict[str, object]]:
    species_index = fetch_json(f"{BASE_URL}/pokemon-species?limit=2000")
    rows = []
    for index, result in enumerate(species_index["results"], start=1):
        species = fetch_json(str(result["url"]))
        pokedex_number = int(species["id"])
        pokemon_name = english_name(species)
        rows.append(
            {
                "pokedex_number": pokedex_number,
                "pokemon_name": pokemon_name,
                "variant_name": None,
                "form_name": pokemon_name,
                "source_slug": str(species["name"]),
            }
        )
        for variety in species.get("varieties", []):
            pokemon = variety.get("pokemon", {})
            slug = str(pokemon.get("name", ""))
            variant_name = variant_from_slug(slug)
            if not variant_name:
                continue
            rows.append(
                {
                    "pokedex_number": pokedex_number,
                    "pokemon_name": pokemon_name,
                    "variant_name": variant_name,
                    "form_name": slug.replace("-", " ").title(),
                    "source_slug": slug,
                }
            )
        if index % 100 == 0:
            print(f"Fetched {index} species...")
    return rows


def ensure_pokedex_schema(conn: sqlite3.Connection) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(pokedex)").fetchall()}
    columns_to_add = {
        "variant_name": "TEXT",
        "form_name": "TEXT",
        "source_slug": "TEXT",
    }
    for column, column_type in columns_to_add.items():
        if column not in columns:
            conn.execute(f"ALTER TABLE pokedex ADD COLUMN {column} {column_type}")


def import_pokedex(conn: sqlite3.Connection, rows: list[dict[str, object]]) -> None:
    ensure_pokedex_schema(conn)
    conn.executemany(
        """
        INSERT INTO pokedex (
            pokedex_number,
            pokemon_name,
            variant_name,
            form_name,
            source_slug
        )
        VALUES (
            :pokedex_number,
            :pokemon_name,
            :variant_name,
            :form_name,
            :source_slug
        )
        ON CONFLICT(source_slug) DO UPDATE SET
            pokedex_number = excluded.pokedex_number,
            pokemon_name = excluded.pokemon_name,
            variant_name = excluded.variant_name,
            form_name = excluded.form_name
        """,
        rows,
    )


def update_card_links(conn: sqlite3.Connection) -> int:
    pokedex_lookup = {}
    for pokedex_id, pokemon_name, variant_name in conn.execute(
        "SELECT id, pokemon_name, variant_name FROM pokedex"
    ).fetchall():
        pokedex_lookup[(lookup_key(pokemon_name), variant_name)] = pokedex_id

    rows = conn.execute("SELECT id, name FROM cards").fetchall()
    updated = 0
    for card_id, card_name in rows:
        pokemon_name, variant_name = normalize_card_name(str(card_name))
        key = lookup_key(pokemon_name)
        pokedex_id = pokedex_lookup.get((key, variant_name))
        if pokedex_id is None and variant_name is not None:
            pokedex_id = pokedex_lookup.get((key, None))
        if pokedex_id is None:
            continue
        conn.execute(
            "UPDATE cards SET pokedex_id = ? WHERE id = ?",
            (pokedex_id, card_id),
        )
        updated += 1
    return updated


def main() -> None:
    parser = argparse.ArgumentParser(description="Import Pokedex rows and link cards.")
    parser.add_argument(
        "--link-only",
        action="store_true",
        help="Skip fetching PokeAPI and only update cards.pokedex_id from existing pokedex rows.",
    )
    args = parser.parse_args()

    if not DB_PATH.exists():
        raise SystemExit(f"Database not found: {DB_PATH}. Run scripts/init_db.py first.")

    rows = [] if args.link_only else load_pokedex_rows()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        if rows:
            import_pokedex(conn, rows)
        updated_cards = update_card_links(conn)
        pokedex_count = conn.execute("SELECT COUNT(*) FROM pokedex").fetchone()[0]

    print(f"Imported/updated {len(rows)} Pokedex rows into {DB_PATH}")
    print(f"Total Pokedex rows: {pokedex_count}")
    print(f"Updated cards.pokedex_id for {updated_cards} cards")


if __name__ == "__main__":
    main()
