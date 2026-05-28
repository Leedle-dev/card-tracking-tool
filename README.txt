Card Tracking Tool

Project Brief

The Card Tracking Tool is a local-first application for managing, pricing, and evaluating cards intended for resale. The initial focus is Simplified Chinese Pokemon cards, with support for tracking equivalent English, Japanese, and other language prints where applicable.

The long-term goal is to combine inventory tracking, marketplace pricing, image-based card matching, graded card value tracking, and grading expected value calculations into one workflow.

Core Goals

- Maintain a searchable database of cards planned for sale.
- Track raw and graded pricing from sources such as eBay, TCGplayer, CardTrader, and other marketplaces.
- Support image search and visual matching to identify equivalent cards across languages and regions.
- Distinguish normal multilingual equivalents from Chinese-exclusive cards.
- Record graded card prices by grading company and grade.
- Calculate whether grading a card is likely worthwhile compared with selling it raw.

Version 1 Roadmap

1. Local Inventory Database
   - Add, edit, delete, and search cards.
   - Track card name, set, card number, language, condition, quantity, cost basis, and notes.
   - Store card images locally.

2. Manual Pricing Records
   - Record raw card prices manually by marketplace/source.
   - Track date checked, listing type, price, shipping, and notes.
   - Support multiple price records per card.

3. Graded Pricing Records
   - Record graded card sale/listing prices.
   - Track grading company, grade, source, sale price, and date.

4. Grading Expected Value Calculator
   - Compare raw sale value against expected graded value.
   - Include grading fees, shipping, marketplace fees, and expected grade probabilities.
   - Show estimated EV and whether grading appears favorable.

5. Basic Reporting
   - Show inventory count and estimated value.
   - Highlight cards that may be good grading candidates.
   - Identify cards with stale or missing pricing data.

Later Phases

- Automated marketplace lookup for Buy It Now listings and sold comps.
- Image-based matching across card languages and regional prints.
- Cross-language card identity mapping.
- CSV or spreadsheet import/export.
- Pricing refresh jobs and historical price charts.
- Sale priority recommendations based on margin, demand, and grading EV.

Modeling Notes

Grading expected value research lives in modeling/grading_ev/. That folder holds the current grading model assumptions, likely future tables, and the Houndoom case-study template.

Development Notes

This repository starts as a local workspace for planning and building the tool. The preferred first implementation should be easy to run on Windows, use a local database, and keep the earliest version focused on reliable manual workflows before adding marketplace automation.

Local Database

The project uses SQLite for the local database. The schema lives in db/schema.sql, and the local database file is created at data/card_tracker.sqlite.

The database file is intentionally ignored by Git because it will contain local inventory and pricing data.

To initialize or update the local database:

1. Run the database initializer:
   C:\Users\Lee\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe scripts\init_db.py

2. Confirm that data/card_tracker.sqlite exists.

3. Optional: print a quick database summary:
   C:\Users\Lee\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe scripts\db_summary.py

Initial database coverage:

- Cards and card images.
- TCGcollector set catalog entries, with imported cards linked back to their source set.
- Pokedex records for canonical Pokemon identities.
- Illustrator records and card-to-illustrator links for future detail-page enrichment.
- Cross-language or related-print card equivalents.
- Marketplace sources.
- Raw price records.
- Graded price records.
- Grading fee profiles.
- Grading EV assumptions.
- Saved grading EV calculation runs.

Example Imports

Gem Pack Vol. 5 can be imported from TCGcollector as starter reference data:

C:\Users\Lee\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe scripts\import_tcgcollector_set.py --language s-chinese --set-name "Gem Pack Vol. 5"

This importer resolves the requested language and set name from the local set_catalog table, fetches the TCGcollector set page, rebuilds the card rows, downloads card images into data/card_images/, and stores the local image path in SQLite. The original TCGcollector image URL and card page URL are retained as source metadata.

Gem Pack Vol. 5 card numbers are stored in the format "0101/07". The first two digits identify the Pokemon, the third digit is currently always 0, and the fourth digit identifies the variant/holo pattern. Downloaded image files are renamed to match the card number, such as 0101-07.png.

To inspect imported cards:

C:\Users\Lee\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe scripts\list_cards.py Pikachu

To fetch TCGcollector set catalogs for International, Japanese, and Simplified Chinese sets:

C:\Users\Lee\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe scripts\fetch_tcgcollector_sets.py

This writes ignored TSV review files to data/raw_fetches/, including tcgcollector_sets_all.tsv. The set catalog TSV includes source region, TCGcollector set ID, set name, set code, release date text, card count, set URL, and slug.

To load the fetched TCGcollector set catalog into SQLite:

C:\Users\Lee\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe scripts\import_tcgcollector_set_catalog.py
