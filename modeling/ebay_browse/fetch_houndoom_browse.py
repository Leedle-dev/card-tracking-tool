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
        "rate_limits": "https://api.ebay.com/developer/analytics/v1_beta/rate_limit/",
    },
    "sandbox": {
        "token": "https://api.sandbox.ebay.com/identity/v1/oauth2/token",
        "browse_search": "https://api.sandbox.ebay.com/buy/browse/v1/item_summary/search",
        "rate_limits": "https://api.sandbox.ebay.com/developer/analytics/v1_beta/rate_limit/",
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
LANGUAGE_EXCLUSION_TERMS = {
    "english": [
        "Japanese",
        "Japan",
        "JPN",
        "Chinese",
        "Simplified Chinese",
        "S-Chinese",
        "S Chinese",
        "CHN",
    ],
    "japanese": [
        "English",
        "ENG",
        "Chinese",
        "Simplified Chinese",
        "S-Chinese",
        "S Chinese",
        "CHN",
    ],
    "s-chinese": [
        "English",
        "ENG",
        "Japanese",
        "Japan",
        "JPN",
    ],
}

QUERIES = [
    {
        "label": "english_houndoom_shrouded_fable",
        "language": "english",
        "pokemon_name": "Houndoom",
        "card_number": "066/064",
        "set_code": "SFA",
        "set_name": "Shrouded Fable",
        "limit": 200,
    },
    {
        "label": "japanese_houndoom_night_wanderer",
        "language": "japanese",
        "pokemon_name": "Houndoom",
        "card_number": "066/064",
        "set_code": "SV6a",
        "set_name": "Night Wanderer",
        "limit": 200,
    },
    {
        "label": "chinese_houndoom_gem_pack_vol_5",
        "language": "s-chinese",
        "pokemon_name": "Houndoom",
        "card_number": "0807/07",
        "set_code": "CBB5C",
        "set_name": "Gem Pack Vol. 5",
        "limit": 200,
    },
]

TSV_COLUMNS = [
    "query_label",
    "query",
    "result_count",
    "item_id",
    "legacy_item_id",
    "is_variation_listing",
    "item_group_href",
    "item_group_type",
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


def request_json_optional(url: str, headers: dict[str, str]) -> tuple[dict[str, object] | None, str | None]:
    request = Request(url, headers=headers)
    try:
        with urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8")), None
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return None, f"HTTP {exc.code} for {url}: {body}"
    except URLError as exc:
        return None, f"Request failed for {url}: {exc}"
    except json.JSONDecodeError as exc:
        return None, f"Could not decode rate-limit response from {url}: {exc}"


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
            "q": search_query_text(query),
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


def fetch_rate_limits(access_token: str) -> tuple[dict[str, object] | None, str | None]:
    return request_json_optional(
        ENVIRONMENT_URLS[ebay_environment()]["rate_limits"],
        {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        },
    )


def format_rate_limit_lines(payload: dict[str, object] | None, error: str | None) -> list[str]:
    lines = ["", "eBay API rate limits"]
    if error:
        return [*lines, f"Rate limit lookup skipped: {error}"]
    if not payload:
        return [*lines, "Rate limit lookup returned no data."]

    rate_limits = payload.get("rateLimits")
    if not isinstance(rate_limits, list):
        return [*lines, "Rate limit lookup returned an unexpected response shape."]

    browse_groups = []
    for group in rate_limits:
        if not isinstance(group, dict):
            continue
        api_name = str(group.get("apiName", ""))
        api_context = str(group.get("apiContext", ""))
        resources = group.get("resources", [])
        resource_names = [
            str(resource.get("name", ""))
            for resource in resources
            if isinstance(resource, dict)
        ] if isinstance(resources, list) else []
        searchable = " ".join([api_name, api_context, *resource_names]).lower()
        if "browse" in searchable:
            browse_groups.append(group)

    if not browse_groups:
        return [*lines, "No Browse API rate-limit rows were returned."]

    for group in browse_groups:
        api_context = value(group, "apiContext")
        api_name = value(group, "apiName")
        api_version = value(group, "apiVersion")
        lines.append(f"{api_context} {api_name} {api_version}".strip())
        resources = group.get("resources")
        if not isinstance(resources, list):
            continue
        for resource in resources:
            if not isinstance(resource, dict):
                continue
            resource_name = value(resource, "name")
            rates = resource.get("rates")
            if not isinstance(rates, list) or not rates:
                lines.append(f"  {resource_name}: no rate details returned")
                continue
            for rate in rates:
                if not isinstance(rate, dict):
                    continue
                lines.append(
                    "  "
                    f"{resource_name}: "
                    f"used={value(rate, 'count')} "
                    f"limit={value(rate, 'limit')} "
                    f"remaining={value(rate, 'remaining')} "
                    f"reset={value(rate, 'reset')} "
                    f"window_seconds={value(rate, 'timeWindow')}"
                )

    return lines


def value(payload: dict[str, object] | None, key: str) -> str:
    if not isinstance(payload, dict):
        return ""
    item = payload.get(key)
    return "" if item is None else str(item)


def card_number_search_prefix(card_number: str) -> str:
    """Return the searchable card number before a slash delimiter.

    Example:
        card_number_search_prefix("066/064") -> "066"
    """

    return re.split(r"[/\\-]", card_number, maxsplit=1)[0].strip()


def search_query_text(query: dict[str, object]) -> str:
    """Build the eBay search text from card identity fields.

    Example:
        Houndoom 066 Shrouded Fable
    """

    override = str(query.get("query_override") or "").strip()
    if override:
        return override

    query_style = str(query.get("query_style") or "set-name").strip().lower()
    number_prefix = card_number_search_prefix(str(query["card_number"]))
    if query_style == "set-code":
        return " ".join([str(query["pokemon_name"]), number_prefix, str(query["set_code"])])
    if query_style == "set-name-and-code":
        return " ".join([str(query["pokemon_name"]), number_prefix, str(query["set_name"]), str(query["set_code"])])
    if query_style == "name-number":
        return " ".join([str(query["pokemon_name"]), number_prefix])
    if query_style == "full-number-set-code":
        return " ".join([str(query["pokemon_name"]), str(query["card_number"]), str(query["set_code"])])

    return " ".join(
        [
            str(query["pokemon_name"]),
            number_prefix,
            str(query["set_name"]),
        ]
    )


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


def title_has_excluded_language(query: dict[str, object], title: str) -> str | None:
    language = str(query.get("language", "")).lower()
    for term in LANGUAGE_EXCLUSION_TERMS.get(language, []):
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


def manual_calculated_shipping_value(price_text: str) -> str:
    """Return an estimated shipping value for eBay calculated shipping.

    Example:
        $4.99 listing -> 1.00
        $12.00 listing -> 2.00
        $20.00 listing -> 5.00
    """

    price = parse_float(price_text)
    if price is None:
        return "5.00"
    if price < 5:
        return "1.00"
    if price <= 15:
        return "2.00"
    return "5.00"


def shipping_from_options(shipping_options: object, price: dict[str, object]) -> dict[str, str]:
    if not isinstance(shipping_options, list) or not shipping_options:
        return {}

    saw_calculated = False
    saw_free = False
    for option in shipping_options:
        if not isinstance(option, dict):
            continue
        shipping_cost = option.get("shippingCost")
        if isinstance(shipping_cost, dict):
            return {
                "value": value(shipping_cost, "value"),
                "currency": value(shipping_cost, "currency"),
            }

        cost_type = value(option, "shippingCostType").upper()
        if cost_type == "CALCULATED":
            saw_calculated = True
        elif "FREE" in cost_type:
            saw_free = True

    if saw_free:
        return {"value": "0.00", "currency": value(price, "currency") or "USD"}
    if saw_calculated:
        return {
            "value": manual_calculated_shipping_value(value(price, "value")),
            "currency": value(price, "currency") or "USD",
        }
    return {}


def is_variation_listing(item_id: str) -> str:
    parts = item_id.split("|")
    return str(len(parts) == 3 and parts[2] != "0")


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

    excluded_language = title_has_excluded_language(query, title)
    if excluded_language:
        reasons.append(f"title_excluded_language:{excluded_language}")

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
    shipping = shipping_from_options(shipping_options, price)
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
        "query": search_query_text(query),
        "result_count": str(result_count),
        "item_id": value(item, "itemId"),
        "legacy_item_id": value(item, "legacyItemId"),
        "is_variation_listing": is_variation_listing(value(item, "itemId")),
        "item_group_href": value(item, "itemGroupHref"),
        "item_group_type": value(item, "itemGroupType"),
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

    rate_limit_payload, rate_limit_error = fetch_rate_limits(access_token)
    rate_limit_lines = format_rate_limit_lines(rate_limit_payload, rate_limit_error)
    summary_lines.extend(rate_limit_lines)

    rate_limit_path = RAW_DIR / f"{timestamp}_ebay_rate_limits.json"
    if rate_limit_payload is not None:
        rate_limit_path.write_text(json.dumps(rate_limit_payload, indent=2, sort_keys=True), encoding="utf-8")

    summary_path = OUTPUT_DIR / f"{timestamp}_ebay_browse_houndoom_summary.txt"
    summary_path.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")

    print(f"Wrote {len(rows)} rows to {tsv_path}")
    print(f"Wrote {len(accepted_rows)} accepted rows to {filtered_tsv_path}")
    print(f"Wrote {len(rejected_rows)} rejected rows to {rejected_tsv_path}")
    print(f"Wrote summary to {summary_path}")
    print(f"Wrote raw JSON files to {RAW_DIR}")
    for line in rate_limit_lines:
        print(line)


if __name__ == "__main__":
    main()
