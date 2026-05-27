from pathlib import Path
import sqlite3


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "card_tracker.sqlite"


def main() -> None:
    if not DB_PATH.exists():
        raise SystemExit(f"Database not found: {DB_PATH}")

    with sqlite3.connect(DB_PATH) as conn:
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
        ).fetchall()
        sources = conn.execute(
            "SELECT name FROM marketplace_sources ORDER BY name"
        ).fetchall()
        profiles = conn.execute(
            "SELECT name, grading_company FROM grading_profiles ORDER BY name"
        ).fetchall()
        card_counts = conn.execute(
            """
            SELECT set_code, set_name, language, COUNT(*)
            FROM cards
            GROUP BY set_code, set_name, language
            ORDER BY set_code, language
            """
        ).fetchall()

    print("Tables:")
    for (name,) in tables:
        print(f"- {name}")

    print("\nMarketplace sources:")
    for (name,) in sources:
        print(f"- {name}")

    print("\nGrading profiles:")
    for name, company in profiles:
        print(f"- {name} ({company})")

    print("\nCard counts:")
    if not card_counts:
        print("- No cards imported yet")
    for set_code, set_name, language, count in card_counts:
        print(f"- {set_code} | {set_name} | {language}: {count}")


if __name__ == "__main__":
    main()
