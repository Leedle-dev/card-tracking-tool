Grading EV Model

Purpose

This folder holds planning notes, assumptions, and future scripts for grading expected value research. The goal is to keep grading logic separate from general database import work until the model is mature enough to become application code.

Core Model

The grading model should not rely only on manually entered grade probabilities and static sale prices. It should combine:

Current testing assumption: the EV model only evaluates raw cards that already look worth submitting. Cards that do not look submit-worthy are assumed to be sold raw. Detailed local copy condition screening is a later workflow.

1. Grade probability data
   - Observed grade distributions from sources such as GemRate, Beckett population reports, PSA population reports, and other available grading population sources.
   - Separate grade distributions by card, grading company, language, region, and print source when possible.
   - Use Japanese print data as a possible prior for Simplified Chinese cards when Chinese population data is sparse, because both are generally printed in Japan.

2. Market value history
   - Raw card prices over time.
   - Graded card prices by company and grade.
   - Active listings, sold listings, listing counts, sold counts, and age of comps.
   - Separate listing prices from confirmed sale prices.

3. Liquidity and confidence
   - High-population cards with many sales comps should have higher confidence.
   - Low-population cards may have more upside but wider valuation uncertainty.
   - Thin markets should not be averaged blindly. A low listing and a very high listing may signal low liquidity instead of a stable midpoint.

4. Cost and timing
   - Grading fee.
   - Inbound shipping allocation.
   - Return shipping allocation.
   - Marketplace selling fees.
   - Turnaround time and opportunity cost.

Expected Value Formula

At a high level:

Expected graded net =
    sum(probability_of_grade * expected_sale_price_for_grade)
    - grading_fee
    - inbound_shipping_allocation
    - return_shipping_allocation
    - marketplace_fees
    - liquidity_or_confidence_haircut
    - turnaround_opportunity_cost

Grading EV delta =
    expected_graded_net - expected_raw_net

Beckett Notes

Beckett should be modeled with distinct grade outcomes, especially:

- BGS Black Label 10
- BGS Pristine 10
- BGS Gem Mint 9.5
- BGS Mint 9
- BGS 8.5 or lower

Black Label should not be blended with ordinary BGS 10 outcomes. It has a different rarity and market behavior.

Working Grade Difficulty Hierarchy

This hierarchy is for modeling how difficult it is for a submit-worthy card to hit each grade. It is not a resale price hierarchy, cost hierarchy, or universal market preference ranking.

1. BGS Black Label 10
2. CGC Pristine 10
3. BGS Pristine 10
4. PSA 10 / CGC Gem Mint 10
5. BGS 9.5
6. CGC 9.5
7. PSA 9 / BGS 9 / CGC 9
8. Lower grades

Likely Future Tables

- grade_population_snapshots
- market_price_snapshots
- grading_ev_scenarios
- grading_ev_scenario_outputs

Near-Term Approach

Use one rich example first: Houndoom illustration/rare art across Simplified Chinese Gem Pack Vol. 5, English Shrouded Fable, and Japanese Night Wanderer. Build the model around observed grade populations, raw price history, graded listings, sold comps, and confidence notes before generalizing.
