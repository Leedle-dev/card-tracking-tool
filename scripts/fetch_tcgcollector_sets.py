from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen
import argparse
import html
import re


ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw_fetches"
BASE_URL = "https://www.tcgcollector.com"

CATALOGS = {
    "international": "https://www.tcgcollector.com/sets/intl",
    "japanese": "https://www.tcgcollector.com/sets/jp",
    "s-chinese": "https://www.tcgcollector.com/sets/cn",
}

SET_LINK_RE = re.compile(
    r'<a\s+[^>]*href="/sets/(?P<set_id>\d+)/(?P<slug>[^"?]+)(?:\?[^"]*)?"[^>]*>'
    r"(?P<name>[^<]+)</a>",
    re.MULTILINE,
)
SET_CODE_RE = re.compile(
    r'<span[^>]*class="[^"]*set-logo-grid-item-code[^"]*"[^>]*>(?P<code>[^<]+)</span>'
)
DATE_RE = re.compile(r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{2},\s+\d{4}\b")
COUNT_RE = re.compile(r"\b0/(?P<count>\d+)\b")


def fetch(url: str) -> tuple[int | None, dict[str, str], bytes]:
    request = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    try:
        with urlopen(request, timeout=30) as response:
            return response.status, dict(response.headers.items()), response.read()
    except HTTPError as exc:
        return exc.code, dict(exc.headers.items()), exc.read()
    except URLError as exc:
        raise SystemExit(f"Request failed for {url}: {exc}") from exc


def extract_sets(text: str, region: str) -> list[dict[str, str]]:
    sets_by_id = {}
    for item_html in text.split('<div class="set-logo-grid-item">')[1:]:
        match = SET_LINK_RE.search(item_html)
        if not match:
            continue

        set_id = match.group("set_id")
        if set_id in sets_by_id:
            continue

        name = html.unescape(match.group("name")).strip()
        if not name:
            continue

        code_match = SET_CODE_RE.search(item_html)
        date_match = DATE_RE.search(item_html)
        count_match = COUNT_RE.search(item_html)
        slug = match.group("slug")
        set_url = urljoin(
            BASE_URL,
            f"/sets/{set_id}/{slug}?setCardCountMode=anyCardVariant",
        )

        sets_by_id[set_id] = {
            "source_region": region,
            "tcgcollector_set_id": set_id,
            "set_name": name,
            "set_code": html.unescape(code_match.group("code")).strip() if code_match else "",
            "release_date_text": date_match.group(0) if date_match else "",
            "card_count": count_match.group("count") if count_match else "",
            "set_url": set_url,
            "slug": slug,
        }

    return list(sets_by_id.values())


def write_tsv(path: Path, rows: list[dict[str, str]]) -> None:
    columns = [
        "source_region",
        "tcgcollector_set_id",
        "set_name",
        "set_code",
        "release_date_text",
        "card_count",
        "set_url",
        "slug",
    ]
    lines = ["\t".join(columns)]
    for row in rows:
        lines.append("\t".join(row[column] for column in columns))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def likely_challenge(text: str, parsed_count: int) -> bool:
    lower_text = text.lower()
    return (
        parsed_count == 0
        and (
            "just a moment" in lower_text
            or "enable javascript and cookies" in lower_text
            or "cf-chl" in lower_text
        )
    )


def fetch_catalog(region: str, url: str) -> list[dict[str, str]]:
    status, headers, body = fetch(url)
    text = body.decode("utf-8", errors="replace")

    html_path = RAW_DIR / f"tcgcollector_sets_{region}.html"
    tsv_path = RAW_DIR / f"tcgcollector_sets_{region}.tsv"
    html_path.write_bytes(body)

    rows = extract_sets(text, region)
    write_tsv(tsv_path, rows)

    print(f"{region}:")
    print(f"  URL: {url}")
    print(f"  Status: {status}")
    print(f"  Content-Type: {headers.get('Content-Type', '(missing)')}")
    print(f"  Bytes: {len(body)}")
    print(f"  Raw HTML: {html_path}")
    print(f"  TSV: {tsv_path}")
    print(f"  Extracted sets: {len(rows)}")
    print(f"  Looks like Cloudflare challenge: {likely_challenge(text, len(rows))}")
    if rows:
        print("  First sets:")
        for row in rows[:3]:
            print(
                "   - "
                f"{row['set_name']} | {row['set_code']} | "
                f"{row['release_date_text']} | {row['card_count']} | "
                f"{row['set_url']}"
            )
    print()

    return rows


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch TCGcollector set catalogs for manual review."
    )
    # Argument examples:
    #   --region all
    #   --region s-chinese
    #   --region japanese
    parser.add_argument(
        "--region",
        choices=[*CATALOGS.keys(), "all"],
        default="all",
        help="Catalog region to fetch.",
    )
    args = parser.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)

    regions = CATALOGS.keys() if args.region == "all" else [args.region]
    all_rows = []
    for region in regions:
        all_rows.extend(fetch_catalog(region, CATALOGS[region]))

    if args.region == "all":
        combined_path = RAW_DIR / "tcgcollector_sets_all.tsv"
        write_tsv(combined_path, all_rows)
        print(f"Combined TSV: {combined_path}")
        print(f"Total extracted sets: {len(all_rows)}")


if __name__ == "__main__":
    main()
