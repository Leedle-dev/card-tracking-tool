from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import argparse
import html
import re


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_URL = (
    "https://www.tcgcollector.com/sets/11808/gem-pack-vol-5"
    "?setCardCountMode=anyCardVariant&releaseDateOrder=newToOld&displayAs=images"
)
DEFAULT_OUTPUT = ROOT / "data" / "raw_fetches" / "tcgcollector_gem_pack_vol5.html"

CARD_TILE_RE = re.compile(
    r'<div\s+class="(?=[^"]*card-image-grid-item)[^"]*"'
    r'[\s\S]*?data-card-id="(?P<card_id>\d+)"'
    r'[\s\S]*?</a>',
    re.MULTILINE,
)
CARD_NAME_RE = re.compile(r'title="(?P<full_name>[^"]+)"')
CARD_SLUG_RE = re.compile(r'href="/cards/\d+/(?P<slug>[^"]+)"')
CARD_NUMBER_OVERLAY_RE = re.compile(
    r'<div class="card-image-grid-item-info-overlay-number">\s*'
    r'(?P<card_number>[^<]+?)\s*</div>'
)
RARITY_RE = re.compile(
    r'alt="(?P<rarity>[^"]+)"[^>]+'
    r'class="card-rarity-symbol card-image-grid-item-info-overlay-rarity-symbol"'
)


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
        raise SystemExit(f"Request failed: {exc}") from exc


def extract_cards(text: str) -> list[dict[str, str]]:
    cards_by_id = {}
    for match in CARD_TILE_RE.finditer(text):
        card_html = match.group(0)
        name_match = CARD_NAME_RE.search(card_html)
        slug_match = CARD_SLUG_RE.search(card_html)
        rarity_match = RARITY_RE.search(card_html)
        if not name_match or not slug_match:
            continue

        full_name = html.unescape(name_match.group("full_name"))
        card_number_match = CARD_NUMBER_OVERLAY_RE.search(card_html)
        card_number = (
            html.unescape(card_number_match.group("card_number")).strip()
            if card_number_match
            else ""
        )
        name = full_name.split(" (", 1)[0]
        card_id = match.group("card_id")
        cards_by_id[card_id] = {
            "card_id": card_id,
            "name": name,
            "card_number": card_number,
            "rarity": html.unescape(rarity_match.group("rarity")) if rarity_match else "",
            "full_name": full_name,
            "slug": slug_match.group("slug"),
        }

    return sorted(
        cards_by_id.values(),
        key=lambda card: (card["card_number"], card["card_id"]),
    )


def write_card_summary(output_path: Path, cards: list[dict[str, str]]) -> Path:
    summary_path = output_path.with_suffix(".cards.tsv")
    lines = ["card_id\tset_code\tname\trarity\tslug\tfull_name"]
    for card in cards:
        lines.append(
            "\t".join(
                [
                    card["card_id"],
                    card["card_number"],
                    card["name"],
                    card["rarity"],
                    card["slug"],
                    card["full_name"],
                ]
            )
        )
    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return summary_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch raw TCGcollector HTML for manual inspection."
    )
    # Argument examples:
    #   --url "https://www.tcgcollector.com/sets/11808/gem-pack-vol-5?setCardCountMode=anyCardVariant"
    #   --output data/raw_fetches/tcgcollector_gem_pack_vol5.html
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = ROOT / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)

    status, headers, body = fetch(args.url)
    output_path.write_bytes(body)

    text = body.decode("utf-8", errors="replace")
    lower_text = text.lower()
    cards = extract_cards(text)
    summary_path = write_card_summary(output_path, cards)
    likely_challenge = (
        not cards
        and (
            "just a moment" in lower_text
            or "enable javascript and cookies" in lower_text
            or "cf-chl" in lower_text
        )
    )

    print(f"URL: {args.url}")
    print(f"Status: {status}")
    print(f"Content-Type: {headers.get('Content-Type', '(missing)')}")
    print(f"Bytes: {len(body)}")
    print(f"Saved: {output_path}")
    print(f"Extracted cards: {len(cards)}")
    print(f"Card summary: {summary_path}")
    print(f"Looks like Cloudflare challenge: {likely_challenge}")
    if cards:
        print("\nFirst cards:")
        for card in cards[:5]:
            print(
                f"- {card['card_id']} | {card['card_number']} | "
                f"{card['name']} | {card['rarity']}"
            )
        print("\nLast cards:")
        for card in cards[-5:]:
            print(
                f"- {card['card_id']} | {card['card_number']} | "
                f"{card['name']} | {card['rarity']}"
            )
    print("\nPreview:")
    print(text[:2000])


if __name__ == "__main__":
    main()
