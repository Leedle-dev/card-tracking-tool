from __future__ import annotations

from datetime import datetime
from pathlib import Path
import argparse
import json
import sys

from PIL import Image, ImageOps


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from card_tracker.reporting import ReportBuilder


DEFAULT_LOGO = Path(
    r"C:\Users\Lee\Documents\Card Tracking Tool\reports\listing_assets\logo_assets"
    r"\lees_tcg_collectables_logo_circle.png"
)

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Add a faded-edge eBay shop logo watermark to listing photos.")
    # Argument examples:
    #   python scripts/watermark_ebay_photos.py "C:/Users/Lee/Pictures/ebay_card_business/binder_first_half"
    #   python scripts/watermark_ebay_photos.py "C:/photos/input" --output-dir "C:/photos/input_watermarked"
    #   python scripts/watermark_ebay_photos.py "C:/photos/input" --scale 0.16 --opacity 0.62 --position bottom-right
    parser.add_argument("input_dir", type=Path, help="Folder containing source listing photos.")
    parser.add_argument("--logo", type=Path, default=DEFAULT_LOGO, help="Logo PNG path.")
    parser.add_argument("--output-dir", type=Path, help="Output folder. Defaults to a timestamped report folder.")
    parser.add_argument("--scale", type=float, default=0.16, help="Watermark width as a fraction of photo width.")
    parser.add_argument("--opacity", type=float, default=1.0, help="Maximum watermark opacity from 0.0 to 1.0.")
    parser.add_argument("--fade-ratio", type=float, default=0.18, help="Edge fade width as a fraction of watermark size.")
    parser.add_argument("--margin-ratio", type=float, default=0.035, help="Photo-edge margin as a fraction of photo width.")
    parser.add_argument(
        "--position",
        choices=["bottom-right", "bottom-left", "top-right", "top-left", "center"],
        default="bottom-right",
        help="Watermark placement.",
    )
    parser.add_argument("--quality", type=int, default=95, help="JPEG output quality.")
    parser.add_argument("--max-images", type=int, help="Optional cap for testing.")
    return parser.parse_args()


def resolve_output_dir(args: argparse.Namespace) -> Path:
    if args.output_dir:
        output_dir = args.output_dir if args.output_dir.is_absolute() else ROOT / args.output_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir

    report = ReportBuilder(
        report_type="watermarked_listing_photos",
        label=args.input_dir.name,
        metadata={"source_dir": str(args.input_dir), "logo": str(args.logo)},
    )
    return report.output_dir


def image_files(input_dir: Path) -> list[Path]:
    return sorted(
        [path for path in input_dir.iterdir() if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS],
        key=lambda path: path.name.lower(),
    )


def faded_logo_mask(size: tuple[int, int], opacity: float, fade_ratio: float) -> Image.Image:
    width, height = size
    fade = max(1, int(min(width, height) * fade_ratio))
    max_alpha = int(max(0.0, min(1.0, opacity)) * 255)
    mask = Image.new("L", size, 0)
    pixels = mask.load()
    for y in range(height):
        edge_y = min(y, height - 1 - y)
        for x in range(width):
            edge_x = min(x, width - 1 - x)
            edge_distance = min(edge_x, edge_y)
            factor = min(1.0, edge_distance / fade)
            pixels[x, y] = int(max_alpha * factor)
    return mask


def prepare_watermark(logo_path: Path, target_width: int, opacity: float, fade_ratio: float) -> Image.Image:
    logo = Image.open(logo_path).convert("RGBA")
    ratio = target_width / logo.width
    target_height = max(1, int(logo.height * ratio))
    logo = logo.resize((target_width, target_height), Image.Resampling.LANCZOS)

    original_alpha = logo.getchannel("A")
    fade_mask = faded_logo_mask(logo.size, opacity, fade_ratio)
    combined_alpha = Image.composite(fade_mask, Image.new("L", logo.size, 0), original_alpha)
    logo.putalpha(combined_alpha)
    return logo


def position_for(photo_size: tuple[int, int], watermark_size: tuple[int, int], position: str, margin: int) -> tuple[int, int]:
    photo_width, photo_height = photo_size
    mark_width, mark_height = watermark_size
    if position == "bottom-right":
        return (photo_width - mark_width - margin, photo_height - mark_height - margin)
    if position == "bottom-left":
        return (margin, photo_height - mark_height - margin)
    if position == "top-right":
        return (photo_width - mark_width - margin, margin)
    if position == "top-left":
        return (margin, margin)
    return ((photo_width - mark_width) // 2, (photo_height - mark_height) // 2)


def output_path_for(source: Path, output_dir: Path) -> Path:
    if source.suffix.lower() in {".jpg", ".jpeg"}:
        return output_dir / source.name
    return output_dir / f"{source.stem}.png"


def watermark_image(source: Path, output_dir: Path, logo_path: Path, args: argparse.Namespace) -> Path:
    photo = ImageOps.exif_transpose(Image.open(source)).convert("RGBA")
    watermark_width = max(80, int(photo.width * args.scale))
    watermark = prepare_watermark(logo_path, watermark_width, args.opacity, args.fade_ratio)
    margin = max(20, int(photo.width * args.margin_ratio))
    position = position_for(photo.size, watermark.size, args.position, margin)

    output = photo.copy()
    output.alpha_composite(watermark, position)

    path = output_path_for(source, output_dir)
    if source.suffix.lower() in {".jpg", ".jpeg"}:
        output.convert("RGB").save(path, quality=args.quality, optimize=True)
    else:
        output.save(path)
    return path


def main() -> None:
    args = parse_args()
    input_dir = args.input_dir
    if not input_dir.is_absolute():
        input_dir = ROOT / input_dir
    logo_path = args.logo if args.logo.is_absolute() else ROOT / args.logo

    if not input_dir.exists():
        raise SystemExit(f"Input folder does not exist: {input_dir}")
    if not logo_path.exists():
        raise SystemExit(f"Logo does not exist: {logo_path}")

    output_dir = resolve_output_dir(args)
    files = image_files(input_dir)
    if args.max_images:
        files = files[: args.max_images]
    if not files:
        raise SystemExit(f"No images found in {input_dir}")

    processed = []
    started_at = datetime.now().astimezone().isoformat(timespec="seconds")
    for source in files:
        output_path = watermark_image(source, output_dir, logo_path, args)
        processed.append({"source": str(source), "output": str(output_path)})

    metadata = {
        "started_at": started_at,
        "finished_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "source_dir": str(input_dir),
        "output_dir": str(output_dir),
        "logo": str(logo_path),
        "count": len(processed),
        "scale": args.scale,
        "opacity": args.opacity,
        "fade_ratio": args.fade_ratio,
        "position": args.position,
        "processed": processed,
    }
    (output_dir / "watermark_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    print(f"Watermarked {len(processed)} images.")
    print(output_dir)


if __name__ == "__main__":
    main()
