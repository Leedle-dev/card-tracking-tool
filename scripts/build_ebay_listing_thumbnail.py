from pathlib import Path
import argparse
import math

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PHOTO_DIR = Path(r"C:\Users\Lee\Pictures\ebay_card_business\GemPack5 - CBB5C")
DEFAULT_LOGO = Path(
    r"C:\Users\Lee\.codex\generated_images\019e6a18-6644-7642-8ec4-5b075c71fc8c"
    r"\ig_0ba3a514c03a7cc9016a1f8e8cda54819b8f6a3c629ac704fe.png"
)
DEFAULT_OUTPUT = ROOT / "reports" / "listing_assets" / "gem_pack_vol_5_ebay_thumbnail.png"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build an eBay listing thumbnail for Gem Pack Vol. 5.")
    # Argument examples:
    #   --photo-dir "C:/Users/Lee/Pictures/ebay_card_business/GemPack5 - CBB5C"
    #   --output reports/listing_assets/gem_pack_vol_5_ebay_thumbnail.png
    parser.add_argument("--photo-dir", default=str(DEFAULT_PHOTO_DIR), help="Folder with renamed card photos.")
    parser.add_argument("--logo", default=str(DEFAULT_LOGO), help="Shop logo image path.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output PNG path.")
    return parser.parse_args()


def load_font(name: str, size: int) -> ImageFont.FreeTypeFont:
    for path in [
        Path(r"C:\Windows\Fonts") / name,
        Path(r"C:\Windows\Fonts") / name.lower(),
    ]:
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default(size=size)


def gradient_background(size: int) -> Image.Image:
    image = Image.new("RGB", (size, size))
    pixels = image.load()
    for y in range(size):
        for x in range(size):
            t = (x + y) / (2 * size)
            r = int(29 + 205 * t)
            g = int(34 + 88 * (1 - abs(t - 0.55)))
            b = int(56 + 185 * (1 - t))
            pixels[x, y] = (r, g, b)

    overlay = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for radius, alpha in [(560, 45), (430, 35), (310, 25)]:
        draw.ellipse(
            (size // 2 - radius, size // 2 - radius, size // 2 + radius, size // 2 + radius),
            outline=(255, 255, 255, alpha),
            width=7,
        )
    return Image.alpha_composite(image.convert("RGBA"), overlay)


def crop_card(path: Path) -> Image.Image:
    image = ImageOps.exif_transpose(Image.open(path)).convert("RGBA")
    # Crop the physical card from the consistent photo station framing.
    card = image.crop((1030, 1450, 2050, 3090))
    return card


def add_shadow(image: Image.Image, blur: int = 24, offset: tuple[int, int] = (18, 24)) -> Image.Image:
    shadow = Image.new("RGBA", (image.width + blur * 4, image.height + blur * 4), (0, 0, 0, 0))
    mask = Image.new("L", image.size, 230)
    shadow.paste((0, 0, 0, 180), (blur * 2 + offset[0], blur * 2 + offset[1]), mask)
    shadow = shadow.filter(ImageFilter.GaussianBlur(blur))
    shadow.alpha_composite(image, (blur * 2, blur * 2))
    return shadow


def paste_rotated_card(canvas: Image.Image, card: Image.Image, center: tuple[int, int], height: int, angle: float) -> None:
    ratio = height / card.height
    resized = card.resize((int(card.width * ratio), height), Image.Resampling.LANCZOS)
    framed = add_shadow(resized)
    rotated = framed.rotate(angle, expand=True, resample=Image.Resampling.BICUBIC)
    x = center[0] - rotated.width // 2
    y = center[1] - rotated.height // 2
    canvas.alpha_composite(rotated, (x, y))


def text_with_stroke(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    font: ImageFont.FreeTypeFont,
    fill: str,
    stroke_width: int = 8,
    stroke_fill: str = "black",
    anchor: str = "mm",
) -> None:
    draw.text(
        xy,
        text,
        font=font,
        fill=fill,
        stroke_width=stroke_width,
        stroke_fill=stroke_fill,
        anchor=anchor,
    )


def fit_logo(path: Path, size: int) -> Image.Image:
    logo = Image.open(path).convert("RGBA")
    logo.thumbnail((size, size), Image.Resampling.LANCZOS)
    badge = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    x = (size - logo.width) // 2
    y = (size - logo.height) // 2
    badge.alpha_composite(logo, (x, y))
    return badge


def main() -> None:
    args = parse_args()
    photo_dir = Path(args.photo_dir)
    logo_path = Path(args.logo)
    output = Path(args.output)
    if not output.is_absolute():
        output = ROOT / output

    selected_cards = [
        "0101-07-Captain Pikachu.jpg",
        "0205-07-Hisuian Growlithe.jpg",
        "0305-07-Magneton.jpg",
        "0805-07-Houndoom.jpg",
        "2205-07-Floragato.jpg",
    ]
    cards = [crop_card(photo_dir / filename) for filename in selected_cards]

    size = 1600
    canvas = gradient_background(size)

    paste_rotated_card(canvas, cards[0], (330, 570), 820, -17)
    paste_rotated_card(canvas, cards[1], (1260, 590), 820, 15)
    paste_rotated_card(canvas, cards[2], (590, 520), 780, -7)
    paste_rotated_card(canvas, cards[3], (1010, 515), 780, 7)
    paste_rotated_card(canvas, cards[4], (800, 610), 900, 0)

    draw = ImageDraw.Draw(canvas)
    impact = load_font("impact.ttf", 152)
    impact_small = load_font("impact.ttf", 84)
    arial_bold = load_font("arialbd.ttf", 64)

    # Top badges.
    draw.rounded_rectangle((40, 40, 320, 135), radius=32, fill=(12, 20, 32, 220), outline=(255, 214, 92, 255), width=5)
    draw.text((180, 89), "CBB5C", font=arial_bold, fill=(255, 224, 99), anchor="mm")

    logo = fit_logo(logo_path, 265)
    canvas.alpha_composite(logo, (1290, 28))

    # Bottom readable listing text.
    draw.rounded_rectangle((0, 1165, 1600, 1600), radius=0, fill=(0, 0, 0, 120))
    text_with_stroke(draw, (800, 1250), "GEM PACK VOL. 5", impact, "white", stroke_width=10)
    text_with_stroke(draw, (470, 1425), "CHOOSE YOUR CARD", impact_small, "#ff5a19", stroke_width=7)
    text_with_stroke(draw, (1160, 1425), "FAST US SHIPPING", impact_small, "#1ee6e6", stroke_width=7)

    draw.rounded_rectangle((635, 1058, 965, 1130), radius=24, fill=(255, 224, 99, 235), outline=(12, 20, 32, 255), width=4)
    draw.text((800, 1094), "S-CHINESE", font=load_font("arialbd.ttf", 44), fill=(12, 20, 32), anchor="mm")

    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(output, quality=95)
    print(output)


if __name__ == "__main__":
    main()
