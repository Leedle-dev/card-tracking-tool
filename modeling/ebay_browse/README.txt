eBay Browse API Exploration

This folder holds exploratory eBay Browse API fetches for card pricing research.

Credentials

Set one of these before running:

- EBAY_ACCESS_TOKEN
- EBAY_CLIENT_ID and EBAY_CLIENT_SECRET

The script uses the eBay production Browse API by default. It fetches active
listings only; sold-listing research will need a separate source/API.

Example

C:\Users\Lee\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe modeling\ebay_browse\fetch_houndoom_browse.py

Outputs

- output\YYYYMMDD_HHMMSS_ebay_browse_houndoom_results.tsv
- output\YYYYMMDD_HHMMSS_ebay_browse_houndoom_summary.txt
- output\raw\YYYYMMDD_HHMMSS_LABEL.json

