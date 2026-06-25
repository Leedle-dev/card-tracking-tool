from pathlib import Path
import argparse
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageOps

from test_card_crop_detector import detect_card_bbox, parse_search_box as parse_pil_search_box


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from card_tracker.report_paths import timestamped_report_dir

DEFAULT_PHOTO_DIR = Path(r"C:\Users\Lee\Pictures\ebay_card_business\GemPack5 - CBB5C")
DEFAULT_INPUT = DEFAULT_PHOTO_DIR / "0101-07-Captain Pikachu.jpg"

THUMBNAIL_CARD_FILES = [
    "0101-07-Captain Pikachu.jpg",
    "0205-07-Hisuian Growlithe.jpg",
    "0305-07-Magneton.jpg",
    "0805-07-Houndoom.jpg",
    "2205-07-Floragato.jpg",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract scan-like Pokemon card cutouts from black-backdrop photos.")
    # Argument examples:
    #   python scripts/extract_card_scan_like.py
    #   python scripts/extract_card_scan_like.py --batch-thumbnail-cards
    #   python scripts/extract_card_scan_like.py --input "C:/Users/Lee/Pictures/ebay_card_business/GemPack5 - CBB5C/0805-07-Houndoom.jpg"
    #   python scripts/extract_card_scan_like.py --search-box 850,1200,2250,3400 --output-width 1100
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="Single card photo to process.")
    parser.add_argument("--photo-dir", type=Path, default=DEFAULT_PHOTO_DIR, help="Photo folder for batch modes.")
    parser.add_argument("--output-dir", type=Path, help="Folder for generated PNGs.")
    parser.add_argument(
        "--report-label",
        default="gem_pack_vol_5_scan_like_cards",
        help="Label for the generated timestamped report folder when --output-dir is omitted.",
    )
    parser.add_argument("--batch-thumbnail-cards", action="store_true", help="Process the five cards used in the thumbnail.")
    parser.add_argument(
        "--method",
        choices=["tight-crop", "perspective"],
        default="tight-crop",
        help="Extraction method. tight-crop is cleaner for the current photo station; perspective is experimental.",
    )
    parser.add_argument("--search-box", default="850,1200,2250,3400", help="Rough source-image search box: left,top,right,bottom.")
    parser.add_argument("--threshold", type=int, default=55, help="Brightness threshold for separating card from backdrop.")
    parser.add_argument("--output-width", type=int, default=1100, help="Output card width in pixels.")
    parser.add_argument("--card-aspect", type=float, default=0.716, help="Physical card width divided by height.")
    parser.add_argument("--corner-radius", type=int, default=54, help="Rounded alpha mask radius in output pixels.")
    parser.add_argument("--bottom-crop-px", type=int, default=0, help="Optional manual bottom crop after extraction.")
    return parser.parse_args()


def parse_search_box(text: str, image: np.ndarray) -> tuple[int, int, int, int]:
    if text.strip().lower() == "full":
        return (0, 0, image.shape[1], image.shape[0])
    parts = [int(part.strip()) for part in text.split(",")]
    if len(parts) != 4:
        raise ValueError("--search-box must be left,top,right,bottom or full")
    left, top, right, bottom = parts
    return (
        max(0, left),
        max(0, top),
        min(image.shape[1], right),
        min(image.shape[0], bottom),
    )


def order_points(points: np.ndarray) -> np.ndarray:
    points = points.astype("float32")
    sums = points.sum(axis=1)
    diffs = np.diff(points, axis=1).reshape(-1)
    return np.array(
        [
            points[np.argmin(sums)],
            points[np.argmin(diffs)],
            points[np.argmax(sums)],
            points[np.argmax(diffs)],
        ],
        dtype="float32",
    )


def build_search_mask(search: np.ndarray, threshold: int) -> np.ndarray:
    gray = cv2.cvtColor(search, cv2.COLOR_RGB2GRAY)
    _, mask = cv2.threshold(gray, threshold, 255, cv2.THRESH_BINARY)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((13, 13), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    return mask


def find_card_box_and_alpha(
    image: np.ndarray,
    search_box: tuple[int, int, int, int],
    threshold: int,
    card_aspect: float,
) -> tuple[np.ndarray, np.ndarray]:
    left, top, right, bottom = search_box
    search = image[top:bottom, left:right]
    mask = build_search_mask(search, threshold)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    candidates = []
    for contour in contours:
        area = cv2.contourArea(contour)
        if area < 50_000:
            continue
        rect = cv2.minAreaRect(contour)
        width, height = rect[1]
        if width == 0 or height == 0:
            continue
        aspect = min(width, height) / max(width, height)
        aspect_error = abs(aspect - card_aspect)
        if aspect_error > 0.12:
            continue
        candidates.append((area - aspect_error * 500_000, rect, contour))

    if not candidates:
        raise RuntimeError("Could not find a card-shaped contour.")

    _, best_rect, best_contour = max(candidates, key=lambda item: item[0])
    box = cv2.boxPoints(best_rect)
    box[:, 0] += left
    box[:, 1] += top

    full_alpha = np.zeros(image.shape[:2], dtype=np.uint8)
    contour_mask = np.zeros(mask.shape, dtype=np.uint8)
    cv2.drawContours(contour_mask, [best_contour], -1, 255, thickness=cv2.FILLED)
    contour_mask = cv2.morphologyEx(contour_mask, cv2.MORPH_CLOSE, np.ones((17, 17), np.uint8))
    contour_mask = cv2.GaussianBlur(contour_mask, (9, 9), 0)
    full_alpha[top:bottom, left:right] = contour_mask

    return order_points(box), full_alpha


def warp_card(
    image: np.ndarray,
    alpha: np.ndarray,
    box: np.ndarray,
    output_width: int,
    card_aspect: float,
) -> Image.Image:
    output_height = int(round(output_width / card_aspect))
    destination = np.array(
        [
            [0, 0],
            [output_width - 1, 0],
            [output_width - 1, output_height - 1],
            [0, output_height - 1],
        ],
        dtype="float32",
    )
    transform = cv2.getPerspectiveTransform(box, destination)
    warped = cv2.warpPerspective(image, transform, (output_width, output_height), flags=cv2.INTER_CUBIC)
    warped_alpha = cv2.warpPerspective(alpha, transform, (output_width, output_height), flags=cv2.INTER_CUBIC)
    output = Image.fromarray(warped).convert("RGBA")
    output.putalpha(Image.fromarray(warped_alpha, mode="L"))
    return output


def apply_rounded_alpha(image: Image.Image, radius: int) -> Image.Image:
    output = image.convert("RGBA")
    mask = Image.new("L", output.size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle((0, 0, output.width - 1, output.height - 1), radius=radius, fill=255)
    output.putalpha(mask)
    return output


def make_checker_preview(image: Image.Image) -> Image.Image:
    preview = Image.new("RGBA", image.size, (172, 245, 218, 255))
    draw = ImageDraw.Draw(preview)
    step = max(50, image.width // 12)
    for y in range(0, image.height, step):
        for x in range(0, image.width, step):
            if (x // step + y // step) % 2 == 0:
                draw.rectangle((x, y, x + step - 1, y + step - 1), fill=(202, 172, 255, 255))
    preview.alpha_composite(image)
    return preview.convert("RGB")


def draw_debug_overlay(image: np.ndarray, search_box: tuple[int, int, int, int], box: np.ndarray) -> Image.Image:
    overlay = Image.fromarray(image).convert("RGB")
    draw = ImageDraw.Draw(overlay)
    draw.rectangle(search_box, outline=(80, 180, 255), width=12)
    points = [tuple(point) for point in box.astype(int)]
    draw.line([*points, points[0]], fill=(255, 60, 60), width=14)
    overlay.thumbnail((1200, 1200), Image.Resampling.LANCZOS)
    return overlay


def process_file(path: Path, output_dir: Path, args: argparse.Namespace) -> None:
    pil_image = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    image = np.asarray(pil_image)
    search_box = parse_search_box(args.search_box, image)
    if args.method == "perspective":
        box, alpha = find_card_box_and_alpha(image, search_box, args.threshold, args.card_aspect)
        extracted = warp_card(image, alpha, box, args.output_width, args.card_aspect)
        debug = draw_debug_overlay(image, search_box, box)
    else:
        pil_search_box = parse_pil_search_box(args.search_box, pil_image)
        bbox = detect_card_bbox(pil_image, pil_search_box, args.threshold, 0.25, 0, args.card_aspect)
        extracted = pil_image.crop(bbox).resize(
            (args.output_width, int(round(args.output_width / args.card_aspect))),
            Image.Resampling.LANCZOS,
        ).convert("RGBA")
        debug = pil_image.copy()
        debug_draw = ImageDraw.Draw(debug)
        debug_draw.rectangle(pil_search_box, outline=(80, 180, 255), width=12)
        debug_draw.rectangle(bbox, outline=(255, 60, 60), width=14)
        debug.thumbnail((1200, 1200), Image.Resampling.LANCZOS)

    if args.bottom_crop_px:
        extracted = extracted.crop((0, 0, extracted.width, max(1, extracted.height - args.bottom_crop_px)))
    transparent = apply_rounded_alpha(extracted, args.corner_radius)

    output_dir.mkdir(parents=True, exist_ok=True)
    stem = path.stem
    transparent_path = output_dir / f"{stem}_scan_like_transparent.png"
    preview_path = output_dir / f"{stem}_scan_like_preview.jpg"
    debug_path = output_dir / f"{stem}_scan_like_debug.jpg"

    transparent.save(transparent_path)
    make_checker_preview(transparent).save(preview_path, quality=95)
    debug.save(debug_path, quality=95)

    print(f"{path.name}")
    print(f"  transparent: {transparent_path}")
    print(f"  preview: {preview_path}")
    print(f"  debug: {debug_path}")


def main() -> None:
    args = parse_args()
    output_dir = args.output_dir
    if output_dir is None:
        output_dir = timestamped_report_dir("scan_like_cards", args.report_label)
    elif not output_dir.is_absolute():
        output_dir = ROOT / output_dir

    if args.batch_thumbnail_cards:
        for filename in THUMBNAIL_CARD_FILES:
            process_file(args.photo_dir / filename, output_dir, args)
        return

    process_file(args.input, output_dir, args)


if __name__ == "__main__":
    main()
