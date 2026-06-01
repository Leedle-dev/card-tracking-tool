from __future__ import annotations

from base64 import b64encode
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import csv
import json
import os
import re
import unicodedata


ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = Path(__file__).resolve().parent / "output"
RAW_DIR = OUTPUT_DIR / "raw"

ENVIRONMENT_URLS = {
    "production": {
        "token": "https://api.ebay.com/identity/v1/oauth2/token",
        "browse_search": "https://api.ebay.com/buy/browse/v1/item_summary/search",
    },
    "sandbox": {
        "token": "https://api.sandbox.ebay.com/identity/v1/oauth2/token",
        "browse_search": "https://api.sandbox.ebay.com/buy/browse/v1/item_summary/search",
    },
}
MARKETPLACE_ID = "EBAY_US"
MIN_SELLER_FEEDBACK_SCORE = 10
MIN_SELLER_FEEDBACK_PERCENTAGE = 89.0
EXCLUDED_MARKET_TERMS = [
    "Korea",
    "Korean",
    "Indonesia",
    "Indonesian",
    "Thai",
    "Thailand",
    "Traditional Chinese",
    "Chinese Traditional",
    "Taiwan",
    "Taiwanese",
    "Hong Kong",
    "Italy",
    "Italian",
    "ITA",
]

QUERIES = [
    {
        "label": "english_houndoom_shrouded_fable",
        "query": "Houndoom 066/064 SFA",
        "pokemon_name": "Houndoom",
        "card_number": "066/064",
        "set_code": "SFA",
        "set_name": "Shrouded Fable",
        "limit": 50,
    },
    {
        "label": "japanese_houndoom_night_wanderer",
        "query": "Houndoom 066/064 SV6a",
        "pokemon_name": "Houndoom",
        "card_number": "066/064",
        "set_code": "SV6a",
        "set_name": "Night Wanderer",
        "limit": 50,
    },
    {
        "label": "chinese_houndoom_gem_pack_vol_5",
        "query": "Houndoom 0807/07 CBB5C",
        "pokemon_name": "Houndoom",
        "card_number": "0807/07",
        "set_code": "CBB5C",
        "set_name": "Gem Pack Vol. 5",
        "limit": 50,
    },
]

TSV_COLUMNS = [
    "query_label",
    "query",
    "result_count",
    "item_id",
    "legacy_item_id",
    "title",
    "condition",
    "buying_options",
    "price_value",
    "price_currency",
    "shipping_value",
    "shipping_currency",
    "total_value",
    "total_currency",
    "seller_feedback_score",
    "seller_feedback_percentage",
    "item_location_country",
    "item_location_postal_code",
    "category_id",
    "category_name",
    "item_creation_date",
    "item_end_date",
    "image_url",
    "item_web_url",
]
FILTERED_TSV_COLUMNS = [*TSV_COLUMNS, "filter_reasons", "filter_warnings"]


def request_bytes(url: str, headers: dict[str, str], data: bytes | None = None) -> bytes:
    request = Request(url, headers=headers, data=data)
    try:
        with urlopen(request, timeout=30) as response:
            return response.read()
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"HTTP {exc.code} for {url}\n{body}") from exc
    except URLError as exc:
        raise SystemExit(f"Request failed for {url}: {exc}") from exc


def ebay_environment() -> str:
    """Return the eBay environment to use.

    Example:
        $env:EBAY_ENV="sandbox"
        $env:EBAY_ENV="production"
    """

    environment = os.getenv("EBAY_ENV", "production").lower().strip()
    if environment not in ENVIRONMENT_URLS:
        choices = ", ".join(sorted(ENVIRONMENT_URLS))
        raise SystemExit(f"Unsupported EBAY_ENV={environment!r}. Expected one of: {choices}")
    return environment


def app_access_token() -> str:
    """Return an app access token from either EBAY_ACCESS_TOKEN or app keys.

    Example:
        $env:EBAY_CLIENT_ID="your-client-id"
        $env:EBAY_CLIENT_SECRET="your-client-secret"
    """

    token = os.getenv("EBAY_ACCESS_TOKEN")
    if token:
        return token

    client_id = os.getenv("EBAY_CLIENT_ID")
    client_secret = os.getenv("EBAY_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise SystemExit(
            "Missing eBay credentials. Set EBAY_ACCESS_TOKEN, or set both "
            "EBAY_CLIENT_ID and EBAY_CLIENT_SECRET."
        )

    credentials = b64encode(f"{client_id}:{client_secret}".encode("utf-8")).decode("ascii")
    body = urlencode(
        {
            "grant_type": "client_credentials",
            "scope": "https://api.ebay.com/oauth/api_scope",
        }
    ).encode("utf-8")
    response = request_bytes(
        ENVIRONMENT_URLS[ebay_environment()]["token"],
        {
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        body,
    )
    payload = json.loads(response.decode("utf-8"))
    return payload["access_token"]


def browse_search(access_token: str, query: dict[str, object]) -> dict[str, object]:
    params = urlencode(
        {
            "q": str(query["query"]),
            "limit": int(query["limit"]),
        }
    )
    response = request_bytes(
        f"{ENVIRONMENT_URLS[ebay_environment()]['browse_search']}?{params}",
        {
            "Authorization": f"Bearer {access_token}",
            "X-EBAY-C-MARKETPLACE-ID": MARKETPLACE_ID,
            "Accept": "application/json",
        },
    )
    return json.loads(response.decode("utf-8"))


def value(payload: dict[str, object] | None, key: str) -> str:
    if not isinstance(payload, dict):
        return ""
    item = payload.get(key)
    return "" if item is None else str(item)


def normalized_search_text(text: str) -> str:
    """Normalize listing text before regex matching.

    Example:
        normalized_search_text("Pokémon Houndoom 066/064 SFA")
    """

    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return ascii_text.lower()


def title_has_token(title: str, token: str) -> bool:
    token_pattern = re.escape(normalized_search_text(token))
    return bool(re.search(rf"(?<![a-z0-9]){token_pattern}(?![a-z0-9])", normalized_search_text(title)))


def title_has_card_number(title: str, card_number: str) -> bool:
    title_text = normalized_search_text(title)
    full_number_pattern = re.escape(card_number.lower())
    if re.search(rf"(?<![0-9]){full_number_pattern}(?![0-9])", title_text):
        return True

    leading_number = card_number.split("/", 1)[0].lstrip("0") or "0"
    padded_number = card_number.split("/", 1)[0]
    leading_pattern = rf"(?:#|no\.?\s*)?0*{re.escape(leading_number)}"
    padded_pattern = re.escape(padded_number)
    return bool(
        re.search(rf"(?<![0-9]){leading_pattern}(?![0-9])", title_text)
        or re.search(rf"(?<![0-9]){padded_pattern}(?![0-9])", title_text)
    )


def title_has_set_identity(title: str, set_code: str, set_name: str) -> bool:
    return title_has_token(title, set_code) or title_has_phrase(title, set_name)


def title_has_excluded_market(title: str) -> str | None:
    for term in EXCLUDED_MARKET_TERMS:
        if title_has_phrase(title, term):
            return term
    return None


def title_has_phrase(title: str, phrase: str) -> bool:
    title_text = normalized_search_text(title)
    phrase_parts = re.findall(r"[a-z0-9]+", normalized_search_text(phrase))
    flexible_phrase = r"\W+".join(re.escape(part) for part in phrase_parts)
    return bool(re.search(rf"(?<![a-z0-9]){flexible_phrase}(?![a-z0-9])", title_text))


def parse_float(text: str) -> float | None:
    try:
        return float(text.replace(",", "").strip())
    except ValueError:
        return None


def filter_reasons(query: dict[str, object], row: dict[str, str]) -> list[str]:
    reasons = []
    title = row["title"]
    pokemon_name = str(query["pokemon_name"])
    card_number = str(query["card_number"])

    if not title_has_token(title, pokemon_name):
        reasons.append(f"title_missing_pokemon:{pokemon_name}")
    if not title_has_card_number(title, card_number):
        reasons.append(f"title_missing_card_number:{card_number}")

    excluded_market = title_has_excluded_market(title)
    if excluded_market:
        reasons.append(f"title_excluded_market:{excluded_market}")

    feedback_score = parse_float(row["seller_feedback_score"])
    if feedback_score is None or feedback_score < MIN_SELLER_FEEDBACK_SCORE:
        reasons.append(f"seller_feedback_score_below_{MIN_SELLER_FEEDBACK_SCORE}")

    feedback_percentage = parse_float(row["seller_feedback_percentage"])
    if feedback_percentage is None or feedback_percentage < MIN_SELLER_FEEDBACK_PERCENTAGE:
        reasons.append(f"seller_feedback_percentage_below_{MIN_SELLER_FEEDBACK_PERCENTAGE:g}")

    return reasons


def filter_warnings(query: dict[str, object], row: dict[str, str]) -> list[str]:
    warnings = []
    set_code = str(query["set_code"])
    set_name = str(query["set_name"])

    if not title_has_set_identity(row["title"], set_code, set_name):
        warnings.append(f"title_missing_set_identity:{set_code}_or_{set_name}")

    return warnings


def flatten_item(query: dict[str, object], result_count: int, item: dict[str, object]) -> dict[str, str]:
    price = item.get("price") if isinstance(item.get("price"), dict) else {}
    shipping_options = item.get("shippingOptions")
    shipping = {}
    if isinstance(shipping_options, list) and shipping_options:
        shipping_cost = shipping_options[0].get("shippingCost")
        if isinstance(shipping_cost, dict):
            shipping = shipping_cost
    seller = item.get("seller") if isinstance(item.get("seller"), dict) else {}
    location = item.get("itemLocation") if isinstance(item.get("itemLocation"), dict) else {}
    category = item.get("categoryPath")
    leaf_category = {}
    if isinstance(category, str) and "|" in category:
        leaf = category.split("|")[-1]
        if ":" in leaf:
            category_id, category_name = leaf.split(":", 1)
            leaf_category = {"categoryId": category_id, "categoryName": category_name}
    image = item.get("image") if isinstance(item.get("image"), dict) else {}

    return {
        "query_label": str(query["label"]),
        "query": str(query["query"]),
        "result_count": str(result_count),
        "item_id": value(item, "itemId"),
        "legacy_item_id": value(item, "legacyItemId"),
        "title": value(item, "title"),
        "condition": value(item, "condition"),
        "buying_options": ",".join(item.get("buyingOptions", []))
        if isinstance(item.get("buyingOptions"), list)
        else "",
        "price_value": value(price, "value"),
        "price_currency": value(price, "currency"),
        "shipping_value": value(shipping, "value"),
        "shipping_currency": value(shipping, "currency"),
        "total_value": value(item.get("totalPrice"), "value")
        if isinstance(item.get("totalPrice"), dict)
        else "",
        "total_currency": value(item.get("totalPrice"), "currency")
        if isinstance(item.get("totalPrice"), dict)
        else "",
        "seller_feedback_score": value(seller, "feedbackScore"),
        "seller_feedback_percentage": value(seller, "feedbackPercentage"),
        "item_location_country": value(location, "country"),
        "item_location_postal_code": value(location, "postalCode"),
        "category_id": value(leaf_category, "categoryId"),
        "category_name": value(leaf_category, "categoryName"),
        "item_creation_date": value(item, "itemCreationDate"),
        "item_end_date": value(item, "itemEndDate"),
        "image_url": value(image, "imageUrl"),
        "item_web_url": value(item, "itemWebUrl"),
    }


def main() -> None:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    access_token = app_access_token()
    rows = []
    accepted_rows = []
    rejected_rows = []
    summary_lines = [
        "eBay Browse API Houndoom search",
        f"Fetched at UTC: {timestamp}",
        f"Environment: {ebay_environment()}",
        f"Marketplace: {MARKETPLACE_ID}",
        f"Minimum seller feedback score: {MIN_SELLER_FEEDBACK_SCORE}",
        f"Minimum seller feedback percentage: {MIN_SELLER_FEEDBACK_PERCENTAGE:g}",
        "",
    ]

    for query in QUERIES:
        payload = browse_search(access_token, query)
        raw_path = RAW_DIR / f"{timestamp}_{query['label']}.json"
        raw_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

        items = payload.get("itemSummaries", [])
        if not isinstance(items, list):
            items = []
        result_count = int(payload.get("total", len(items)) or 0)
        query_accepted = 0
        query_rejected = 0
        for item in items:
            if isinstance(item, dict):
                row = flatten_item(query, result_count, item)
                rows.append(row)
                reasons = filter_reasons(query, row)
                warnings = filter_warnings(query, row)
                filtered_row = {
                    **row,
                    "filter_reasons": ";".join(reasons),
                    "filter_warnings": ";".join(warnings),
                }
                if reasons:
                    rejected_rows.append(filtered_row)
                    query_rejected += 1
                else:
                    accepted_rows.append(filtered_row)
                    query_accepted += 1
        summary_lines.append(
            f"{query['label']}: total={result_count}, exported={len(items)}, "
            f"accepted={query_accepted}, rejected={query_rejected}"
        )

    tsv_path = OUTPUT_DIR / f"{timestamp}_ebay_browse_houndoom_results.tsv"
    with tsv_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=TSV_COLUMNS, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)

    filtered_tsv_path = OUTPUT_DIR / f"{timestamp}_ebay_browse_houndoom_filtered_results.tsv"
    with filtered_tsv_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=FILTERED_TSV_COLUMNS, delimiter="\t")
        writer.writeheader()
        writer.writerows(accepted_rows)

    rejected_tsv_path = OUTPUT_DIR / f"{timestamp}_ebay_browse_houndoom_rejected_results.tsv"
    with rejected_tsv_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=FILTERED_TSV_COLUMNS, delimiter="\t")
        writer.writeheader()
        writer.writerows(rejected_rows)

    summary_path = OUTPUT_DIR / f"{timestamp}_ebay_browse_houndoom_summary.txt"
    summary_path.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")

    print(f"Wrote {len(rows)} rows to {tsv_path}")
    print(f"Wrote {len(accepted_rows)} accepted rows to {filtered_tsv_path}")
    print(f"Wrote {len(rejected_rows)} rejected rows to {rejected_tsv_path}")
    print(f"Wrote summary to {summary_path}")
    print(f"Wrote raw JSON files to {RAW_DIR}")


if __name__ == "__main__":
    main()
