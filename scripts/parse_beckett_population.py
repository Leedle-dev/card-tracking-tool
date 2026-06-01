from __future__ import annotations

import argparse
import json
import re
import sys


GRADE_BUCKETS = [
    "BGS 7",
    "BGS 7.5",
    "BGS 8",
    "BGS 8.5",
    "BGS 9",
    "BGS 9.5",
    "BGS 10 Pristine",
    "BGS 10 Black Label",
]


SAMPLE_ROW = (
    "Pikachu AR\t173\t3\t0.2%\t99.7%\t1\t0.1%\t99.6%\t4\t0.2%\t99.4%"
    "\t17\t1%\t98.4%\t184\t11.2%\t87.2%\t1,076\t65.5%\t21.7%"
    "\t316\t19.2%\t0%\t41\t2.5%\t1644"
)


def parse_count(value: str) -> int:
    return int(value.replace(",", "").strip())


def parse_percent(value: str) -> float:
    value = value.strip()
    if not value.endswith("%"):
        raise ValueError(f"Expected percent value, got {value!r}")
    return round(float(value[:-1].replace(",", "")) / 100, 4)


def split_row(row: str) -> list[str]:
    if "\t" in row:
        return [part.strip() for part in row.strip().split("\t") if part.strip()]
    return re.split(r"\s{2,}", row.strip())


def parse_beckett_population_row(
    row: str,
    tcgcollector_set_id: int | None = None,
) -> dict[str, object]:
    parts = split_row(row)
    if len(parts) != 26:
        raise ValueError(
            f"Expected 26 fields after splitting Beckett row, found {len(parts)}: {parts}"
        )

    player = parts[0]
    card_number = parts[1]
    total = parse_count(parts[-1])

    grade_rows = []
    cursor = 2
    for grade_label in GRADE_BUCKETS[:-1]:
        grade_rows.append(
            {
                "grade_label": grade_label,
                "population_count": parse_count(parts[cursor]),
                "rate": parse_percent(parts[cursor + 1]),
                "higher_rate": parse_percent(parts[cursor + 2]),
            }
        )
        cursor += 3

    grade_rows.append(
        {
            "grade_label": GRADE_BUCKETS[-1],
            "population_count": parse_count(parts[cursor]),
            "rate": parse_percent(parts[cursor + 1]),
            "higher_rate": None,
        }
    )

    displayed_population_count = sum(row["population_count"] for row in grade_rows)

    return {
        "tcgcollector_set_id": tcgcollector_set_id,
        "player": player,
        "card_number": card_number,
        "population_total": total,
        "displayed_grade_floor": "BGS 7",
        "displayed_population_count": displayed_population_count,
        "below_displayed_grade_count": total - displayed_population_count,
        "grades": grade_rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Parse one tab-delimited Beckett population table row."
    )
    # Argument examples:
    #   --sample
    #   --tcgcollector-set-id 11808 "Pikachu AR\t173\t3\t0.2%..."
    #   paste a row through stdin when no row argument is supplied
    parser.add_argument("--sample", action="store_true", help="Parse the built-in sample row.")
    parser.add_argument(
        "--tcgcollector-set-id",
        type=int,
        help="TCGcollector set ID for the card's source set.",
    )
    parser.add_argument("row", nargs="?", help="One Beckett population row.")
    args = parser.parse_args()

    row = SAMPLE_ROW if args.sample else args.row
    if row is None:
        row = sys.stdin.read()
    parsed = parse_beckett_population_row(
        row,
        tcgcollector_set_id=args.tcgcollector_set_id,
    )
    print(json.dumps(parsed, indent=2))


if __name__ == "__main__":
    main()
