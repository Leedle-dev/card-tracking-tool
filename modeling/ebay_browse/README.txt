eBay Browse API Exploration

This folder holds exploratory eBay Browse API fetches for card pricing research.

Credentials

Set one of these before running:

- EBAY_ACCESS_TOKEN
- EBAY_CLIENT_ID and EBAY_CLIENT_SECRET

The script uses the eBay production Browse API by default. For sandbox keys, set:

$env:EBAY_ENV="sandbox"

For production keys, either omit EBAY_ENV or set:

$env:EBAY_ENV="production"

It fetches active listings only; sold-listing research will need a separate
source/API.

Example

C:\Users\Lee\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe modeling\ebay_browse\fetch_houndoom_browse.py

Generic Set Fetch

To fetch eBay listings for every card in a set already imported into SQLite:

C:\Users\Lee\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe modeling\ebay_browse\fetch_ebay_listings.py --set-code CBB5C --set-name "Gem Pack Vol. 5"

To preview generated queries without calling eBay:

C:\Users\Lee\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe modeling\ebay_browse\fetch_ebay_listings.py --set-code CBB5C --set-name "Gem Pack Vol. 5" --dry-run

For testing a small batch:

C:\Users\Lee\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe modeling\ebay_browse\fetch_ebay_listings.py --set-code CBB5C --set-name "Gem Pack Vol. 5" --max-cards 5

To fetch and immediately ingest the run into SQLite:

C:\Users\Lee\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe modeling\ebay_browse\fetch_ebay_listings.py --set-code CBB5C --set-name "Gem Pack Vol. 5" --ingest

To ingest an existing timestamped run folder:

C:\Users\Lee\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe modeling\ebay_browse\ingest_ebay_listings.py --run-dir modeling\ebay_browse\output\YYYYMMDD_HHMMSS_SET

Older run folders created before metadata support need set fallback arguments:

C:\Users\Lee\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe modeling\ebay_browse\ingest_ebay_listings.py --run-dir modeling\ebay_browse\output\YYYYMMDD_HHMMSS_SET --set-code CBB5C --set-name "Gem Pack Vol. 5"

Outputs

- output\YYYYMMDD_HHMMSS_ebay_browse_houndoom_results.tsv
- output\YYYYMMDD_HHMMSS_ebay_browse_houndoom_summary.txt
- output\YYYYMMDD_HHMMSS_SET\YYYYMMDD_HHMMSS_SET_ebay_listings.tsv
- output\YYYYMMDD_HHMMSS_SET\YYYYMMDD_HHMMSS_SET_ebay_listings_filtered.tsv
- output\YYYYMMDD_HHMMSS_SET\YYYYMMDD_HHMMSS_SET_ebay_listings_rejected.tsv
- output\YYYYMMDD_HHMMSS_SET\YYYYMMDD_HHMMSS_SET_ebay_listings_variations.tsv
- output\YYYYMMDD_HHMMSS_SET\YYYYMMDD_HHMMSS_SET_ebay_listings_summary.txt
- output\YYYYMMDD_HHMMSS_SET\YYYYMMDD_HHMMSS_SET_ebay_listings_metadata.json
- output\YYYYMMDD_HHMMSS_SET\raw\YYYYMMDD_HHMMSS_LABEL.json
- output\raw\YYYYMMDD_HHMMSS_LABEL.json
