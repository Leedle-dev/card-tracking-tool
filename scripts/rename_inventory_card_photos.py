from pathlib import Path
import argparse
import re
import sqlite3


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "card_tracker.sqlite"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rename physical inventory photos using card names and card numbers."
    )
    # Argument examples:
    #   "C:/Users/Lee/Pictures/ebay_card_business/GemPack5 - CBB5C" --set-code CBB5C
    #   "C:/Users/Lee/Pictures/ebay_card_business/GemPack5 - CBB5C" --set-code CBB5C --execute
    #   "C:/Users/Lee/Pictures/ebay_card_business/GemPack5 - CBB5C" --stamped-start-file IMG_20260603_201643_140.jpg
    parser.add_argument("image_dir", help="Folder containing the photos to rename.")
    parser.add_argument("--set-code", default="CBB5C", help="Set code to map from inventory.")
    parser.add_argument(
        "--stamped-start-file",
        default="",
        help="First photo in the stamped rare tail batch, such as IMG_20260603_201643_140.jpg.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually rename files. Without this, only prints a dry-run plan.",
    )
    parser.add_argument(
        "--swap-card-numbers",
        default="",
        help="Swap two mapped card numbers for photo-order mistakes, such as 0404/07=0505/07.",
    )
    return parser.parse_args()


def filesystem_safe(value: str) -> str:
    value = value.replace("/", "-").replace("\\", "-")
    value = re.sub(r'[<>:"|?*]', "", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def fetch_inventory_cards(set_code: str) -> list[sqlite3.Row]:
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(
            """
            SELECT
                c.id AS card_id,
                c.name AS card_name,
                c.card_number,
                c.source_sequence,
                ci.quantity
            FROM card_inventory ci
            JOIN cards c ON c.id = ci.card_id
            JOIN set_catalog sc ON sc.id = c.set_catalog_id
            WHERE sc.set_code = ?
                AND ci.sale_status != 'reference'
                AND ci.quantity > 0
            ORDER BY c.source_sequence, c.card_number, c.id
            """,
            (set_code,),
        ).fetchall()


def target_name(row: sqlite3.Row, extension: str) -> str:
    return f"{filesystem_safe(row['card_name'])}-{filesystem_safe(row['card_number'])}{extension.lower()}"


def build_card_sequence(cards: list[sqlite3.Row], stamped_start_file: str, files: list[Path]) -> list[sqlite3.Row]:
    if not stamped_start_file:
        return cards

    try:
        stamped_start_index = next(
            index for index, file_path in enumerate(files) if file_path.name == stamped_start_file
        )
    except StopIteration as exc:
        raise ValueError(f"Stamped start file was not found: {stamped_start_file}") from exc

    non_stamped = [card for card in cards if not card["card_number"].startswith(("0206",))]
    front_batch = [card for card in cards if card["card_number"][2:4] != "06"]
    stamped_batch = [card for card in cards if card["card_number"][2:4] == "06"]

    if len(front_batch) != stamped_start_index:
        raise ValueError(
            "Photo/card split mismatch: "
            f"{stamped_start_index} files appear before stamped tail, "
            f"but {len(front_batch)} non-stamped inventory cards were found."
        )

    if len(stamped_batch) != len(files) - stamped_start_index:
        raise ValueError(
            "Stamped tail mismatch: "
            f"{len(files) - stamped_start_index} files are in the stamped tail, "
            f"but {len(stamped_batch)} stamped inventory cards were found."
        )

    # A tiny sanity breadcrumb for the special case from the photo session:
    # stamped rares begin with Hisuian Growlithe 0206/07, not Pikachu 0106/07.
    first_stamped = stamped_batch[0]
    if first_stamped["card_number"] != "0206/07":
        raise ValueError(
            "Stamped tail did not start with the expected Hisuian Growlithe 0206/07 card. "
            f"Found {first_stamped['card_name']} {first_stamped['card_number']}."
        )

    return front_batch + stamped_batch


def apply_card_number_swap(cards: list[sqlite3.Row], swap_card_numbers: str) -> list[sqlite3.Row]:
    if not swap_card_numbers:
        return cards

    try:
        left, right = [part.strip() for part in swap_card_numbers.split("=", maxsplit=1)]
    except ValueError as exc:
        raise ValueError("--swap-card-numbers must use CARD_NUMBER=CARD_NUMBER format.") from exc

    left_index = next(
        (index for index, card in enumerate(cards) if card["card_number"] == left),
        None,
    )
    right_index = next(
        (index for index, card in enumerate(cards) if card["card_number"] == right),
        None,
    )

    if left_index is None or right_index is None:
        raise ValueError(f"Could not find both card numbers to swap: {left} and {right}.")

    swapped = list(cards)
    swapped[left_index], swapped[right_index] = swapped[right_index], swapped[left_index]
    return swapped


def main() -> None:
    args = parse_args()
    image_dir = Path(args.image_dir)
    files = sorted([path for path in image_dir.iterdir() if path.is_file()], key=lambda path: path.name)
    cards = fetch_inventory_cards(args.set_code)
    cards = build_card_sequence(cards, args.stamped_start_file, files)
    cards = apply_card_number_swap(cards, args.swap_card_numbers)

    if len(files) != len(cards):
        raise SystemExit(f"Count mismatch: {len(files)} image files, {len(cards)} inventory cards.")

    planned = []
    seen_targets = set()
    for file_path, card in zip(files, cards):
        target = file_path.with_name(target_name(card, file_path.suffix))
        if target.name in seen_targets:
            raise SystemExit(f"Duplicate target filename: {target.name}")
        seen_targets.add(target.name)
        planned.append((file_path, target, card))

    for index, (source, target, card) in enumerate(planned, start=1):
        print(f"{index:03d}: {source.name} -> {target.name}")

    if not args.execute:
        print(f"Dry run only. Planned {len(planned)} renames.")
        return

    temp_paths = []
    for index, (source, _, _) in enumerate(planned, start=1):
        temp = source.with_name(f"__rename_tmp_{index:03d}{source.suffix.lower()}")
        source.rename(temp)
        temp_paths.append(temp)

    for temp, (_, target, _) in zip(temp_paths, planned):
        temp.rename(target)

    print(f"Renamed {len(planned)} files.")


if __name__ == "__main__":
    main()
