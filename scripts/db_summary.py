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
        grading_companies = conn.execute(
            "SELECT abbreviation, name FROM grading_companies ORDER BY abbreviation"
        ).fetchall()
        card_counts = conn.execute(
            """
            SELECT
                COALESCE(sc.set_code, c.set_code),
                COALESCE(sc.set_name, c.set_name),
                COALESCE(sc.language, c.language),
                COUNT(*)
            FROM cards c
            LEFT JOIN set_catalog sc ON sc.id = c.set_catalog_id
            GROUP BY
                COALESCE(sc.set_code, c.set_code),
                COALESCE(sc.set_name, c.set_name),
                COALESCE(sc.language, c.language)
            ORDER BY 1, 3
            """
        ).fetchall()
        image_counts = conn.execute(
            """
            SELECT
                COALESCE(sc.set_code, c.set_code),
                COALESCE(sc.language, c.language),
                COUNT(*)
            FROM card_images ci
            JOIN cards c ON c.id = ci.card_id
            LEFT JOIN set_catalog sc ON sc.id = c.set_catalog_id
            WHERE ci.image_path LIKE 'data/card_images/%'
            GROUP BY
                COALESCE(sc.set_code, c.set_code),
                COALESCE(sc.language, c.language)
            ORDER BY
                COALESCE(sc.set_code, c.set_code),
                COALESCE(sc.language, c.language)
            """
        ).fetchall()
        set_catalog_counts = conn.execute(
            """
            SELECT source_region, COUNT(*)
            FROM set_catalog
            GROUP BY source_region
            ORDER BY source_region
            """
        ).fetchall()
        linked_card_count = conn.execute(
            "SELECT COUNT(*) FROM cards WHERE set_catalog_id IS NOT NULL"
        ).fetchone()[0]
        total_card_count = conn.execute("SELECT COUNT(*) FROM cards").fetchone()[0]
        population_snapshot_counts = conn.execute(
            """
            SELECT grading_company, COUNT(*)
            FROM grade_population_snapshots
            GROUP BY grading_company
            ORDER BY grading_company
            """
        ).fetchall()
        raw_price_count = conn.execute(
            "SELECT COUNT(*) FROM raw_price_records"
        ).fetchone()[0]
        graded_price_count = conn.execute(
            "SELECT COUNT(*) FROM graded_price_records"
        ).fetchone()[0]
        grade_rate_reference_count = conn.execute(
            "SELECT COUNT(*) FROM grade_rate_reference_data"
        ).fetchone()[0]
        grade_rate_group_count = conn.execute(
            "SELECT COUNT(*) FROM grade_rate_reference_groups"
        ).fetchone()[0]

    print("Tables:")
    for (name,) in tables:
        print(f"- {name}")

    print("\nMarketplace sources:")
    for (name,) in sources:
        print(f"- {name}")

    print("\nGrading profiles:")
    for name, company in profiles:
        print(f"- {name} ({company})")

    print("\nGrading companies:")
    if not grading_companies:
        print("- No grading companies seeded yet")
    for abbreviation, name in grading_companies:
        print(f"- {abbreviation}: {name}")

    print("\nCard counts:")
    print(f"- Linked to set catalog: {linked_card_count}/{total_card_count}")
    if not card_counts:
        print("- No cards imported yet")
    for set_code, set_name, language, count in card_counts:
        print(f"- {set_code} | {set_name} | {language}: {count}")

    print("\nLocal image counts:")
    if not image_counts:
        print("- No local image paths recorded yet")
    for set_code, language, count in image_counts:
        print(f"- {set_code} | {language}: {count}")

    print("\nSet catalog counts:")
    if not set_catalog_counts:
        print("- No set catalog rows imported yet")
    for source_region, count in set_catalog_counts:
        print(f"- {source_region}: {count}")

    print("\nPopulation snapshot counts:")
    if not population_snapshot_counts:
        print("- No population snapshots recorded yet")
    for grading_company, count in population_snapshot_counts:
        print(f"- {grading_company}: {count}")

    print("\nPrice record counts:")
    print(f"- Raw: {raw_price_count}")
    print(f"- Graded: {graded_price_count}")

    print("\nGrade rate reference counts:")
    print(f"- Data rows: {grade_rate_reference_count}")
    print(f"- Filter groups: {grade_rate_group_count}")


if __name__ == "__main__":
    main()
