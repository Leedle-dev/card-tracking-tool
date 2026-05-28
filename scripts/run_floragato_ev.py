from pathlib import Path
import sqlite3


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "card_tracker.sqlite"

TARGET_CARD = {
    "language": "Simplified Chinese",
    "set_code": "CBB5C",
    "card_number": "2207/07",
    "name": "Floragato",
}

JAPANESE_PRIOR_CARD = {
    "language": "Japanese",
    "set_code": "SV6a",
    "card_number": "066/064",
    "name": "Houndoom",
}

RAW_SALE_PRICE_CENTS = 3250
RAW_MARKETPLACE_FEE_RATE = 0.1325
GRADED_SALE_SHIPPING_CENTS = 500

GRADE_PRICE_MAP = {
    "BGS 7": (3250, "fallback_to_raw_value_for_below_bgs_9"),
    "BGS 7.5": (3250, "fallback_to_raw_value_for_below_bgs_9"),
    "BGS 8": (3250, "fallback_to_raw_value_for_below_bgs_9"),
    "BGS 8.5": (3250, "fallback_to_raw_value_for_below_bgs_9"),
    "BGS 9": (4500, "manual_bgs_9_estimate"),
    "BGS 9.5": (6500, "manual_bgs_9_5_estimate"),
    "BGS 10 Pristine": (25000, "manual_bgs_10_estimate"),
    "BGS 10 Black Label": (250000, "manual_bgs_black_label_estimate"),
}


def money(cents: int | float) -> str:
    return f"${cents / 100:.2f}"


def find_card(conn: sqlite3.Connection, criteria: dict[str, str]) -> int:
    row = conn.execute(
        """
        SELECT c.id
        FROM cards c
        LEFT JOIN set_catalog sc ON sc.id = c.set_catalog_id
        WHERE
            COALESCE(sc.language, c.language) = ?
            AND COALESCE(sc.set_code, c.set_code) = ?
            AND c.card_number = ?
            AND c.name = ?
        ORDER BY c.tcgcollector_card_id
        LIMIT 1
        """,
        (
            criteria["language"],
            criteria["set_code"],
            criteria["card_number"],
            criteria["name"],
        ),
    ).fetchone()
    if not row:
        raise SystemExit(f"Card not found: {criteria}")
    return row[0]


def grading_profile(conn: sqlite3.Connection) -> dict[str, object]:
    row = conn.execute(
        """
        SELECT
            id,
            grading_fee_cents,
            inbound_shipping_cents,
            return_shipping_cents,
            marketplace_fee_rate
        FROM grading_profiles
        WHERE name = 'BGS Bulk Estimate'
        """
    ).fetchone()
    if not row:
        raise SystemExit("BGS Bulk Estimate profile not found. Run scripts/init_db.py first.")
    return {
        "id": row[0],
        "grading_fee_cents": row[1],
        "inbound_shipping_cents": row[2],
        "return_shipping_cents": row[3],
        "marketplace_fee_rate": row[4],
    }


def japanese_bgs_population_rows(conn: sqlite3.Connection, card_id: int) -> list[dict[str, object]]:
    rows = conn.execute(
        """
        SELECT
            r.grade_label,
            r.population_count,
            r.rate
        FROM grade_population_snapshots s
        JOIN grade_population_snapshot_rows r ON r.snapshot_id = s.id
        WHERE
            s.card_id = ?
            AND s.grading_company = 'BGS'
            AND s.snapshot_label = 'Japanese Houndoom Night Wanderer 066 BGS pop'
        ORDER BY r.id
        """,
        (card_id,),
    ).fetchall()
    if not rows:
        raise SystemExit("Japanese Houndoom BGS population snapshot not found.")
    return [
        {
            "grade_label": grade_label,
            "population_count": population_count,
            "probability": rate,
        }
        for grade_label, population_count, rate in rows
    ]


def main() -> None:
    if not DB_PATH.exists():
        raise SystemExit(f"Database not found: {DB_PATH}. Run scripts/init_db.py first.")

    with sqlite3.connect(DB_PATH) as conn:
        profile = grading_profile(conn)
        target_card_id = find_card(conn, TARGET_CARD)
        japanese_card_id = find_card(conn, JAPANESE_PRIOR_CARD)
        population_rows = japanese_bgs_population_rows(conn, japanese_card_id)

        raw_net = round(RAW_SALE_PRICE_CENTS * (1 - RAW_MARKETPLACE_FEE_RATE))
        grading_cost = (
            profile["grading_fee_cents"]
            + profile["inbound_shipping_cents"]
            + profile["return_shipping_cents"]
        )

        expected_gross = 0.0
        expected_selling_fees = 0.0
        print("Floragato Grading EV Scenario")
        print("Target card: Simplified Chinese Gem Pack Vol. 5 Floragato 2207/07 Triple Rare")
        print("Grade prior: Japanese Night Wanderer Houndoom BGS population snapshot")
        print("Value curve: user-provided S-Chinese Floragato estimates")
        print(f"Raw sale baseline: {money(RAW_SALE_PRICE_CENTS)}")
        print(f"Raw net after {RAW_MARKETPLACE_FEE_RATE:.2%} fee: {money(raw_net)}")
        print(
            "BGS Bulk grading cost: "
            f"{money(profile['grading_fee_cents'])} grading + "
            f"{money(profile['inbound_shipping_cents'])} inbound + "
            f"{money(profile['return_shipping_cents'])} return = {money(grading_cost)}"
        )
        print(f"Graded sale shipping assumption: {money(GRADED_SALE_SHIPPING_CENTS)}")
        print()
        print("Grade outcomes:")

        for row in population_rows:
            grade_label = row["grade_label"]
            probability = row["probability"] or 0.0
            price_cents, note = GRADE_PRICE_MAP[grade_label]
            sale_total_cents = price_cents + GRADED_SALE_SHIPPING_CENTS
            gross_contribution = probability * sale_total_cents
            fee_contribution = gross_contribution * profile["marketplace_fee_rate"]
            expected_gross += gross_contribution
            expected_selling_fees += fee_contribution
            print(
                f"- {grade_label}: {probability:.1%} * "
                f"({money(price_cents)} + {money(GRADED_SALE_SHIPPING_CENTS)} shipping) "
                f"= {money(gross_contribution)} ({note})"
            )

        expected_graded_net = round(expected_gross - expected_selling_fees - grading_cost)
        expected_raw_net = raw_net
        ev_delta = expected_graded_net - expected_raw_net

        conn.execute(
            """
            INSERT INTO grading_ev_runs (
                card_id,
                grading_profile_id,
                raw_sale_price_cents,
                raw_marketplace_fee_rate,
                expected_graded_gross_cents,
                expected_graded_net_cents,
                expected_raw_net_cents,
                grading_ev_delta_cents,
                notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                target_card_id,
                profile["id"],
                RAW_SALE_PRICE_CENTS,
                RAW_MARKETPLACE_FEE_RATE,
                round(expected_gross),
                expected_graded_net,
                expected_raw_net,
                ev_delta,
                (
                    "Sample EV using Japanese Houndoom BGS population as prior, "
                    "user-provided S-Chinese Floragato value estimates, "
                    "raw sale baseline of $32.50, "
                    "and $5 shipping added to graded sale totals."
                ),
            ),
        )

    print()
    print(f"Expected graded gross: {money(expected_gross)}")
    print(f"Expected graded selling fees: {money(expected_selling_fees)}")
    print(f"Expected graded net after fees/costs: {money(expected_graded_net)}")
    print(f"Expected raw net: {money(expected_raw_net)}")
    print(f"Grading EV delta: {money(ev_delta)}")


if __name__ == "__main__":
    main()
