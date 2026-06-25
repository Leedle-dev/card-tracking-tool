from pathlib import Path
import argparse
from collections import deque
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageOps


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from card_tracker.report_paths import timestamped_report_dir

DEFAULT_INPUT = Path(
    r"C:\Users\Lee\Pictures\ebay_card_business\GemPack5 - CBB5C"
    r"\0101-07-Captain Pikachu.jpg"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Test automatic card crop detection on one card photo.")
    # Argument examples:
    #   python scripts/test_card_crop_detector.py
    #   python scripts/test_card_crop_detector.py --input "C:/Users/Lee/Pictures/ebay_card_business/GemPack5 - CBB5C/0805-07-Houndoom.jpg"
    #   python scripts/test_card_crop_detector.py --threshold 55 --padding 10
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="Card photo to detect and crop.")
    parser.add_argument("--output-dir", type=Path, help="Folder for debug outputs.")
    parser.add_argument(
        "--report-label",
        default="card_crop_detector_test",
        help="Label for the generated timestamped report folder when --output-dir is omitted.",
    )
    parser.add_argument("--threshold", type=int, default=55, help="Brightness threshold for separating card from black backdrop.")
    parser.add_argument("--padding", type=int, default=8, help="Padding around detected card crop, in source-image pixels.")
    parser.add_argument("--scale", type=float, default=0.25, help="Detection scale factor for speed.")
    parser.add_argument("--card-aspect", type=float, default=0.716, help="Physical card width divided by height.")
    parser.add_argument("--corner-radius", type=int, default=42, help="Rounded mask corner radius on the final crop.")
    parser.add_argument(
        "--search-box",
        default="850,1200,2250,3400",
        help="Rough source-image search box as left,top,right,bottom. Use 'full' to search the whole image.",
    )
    return parser.parse_args()


def apply_rounded_mask(image: Image.Image, radius: int) -> Image.Image:
    rounded = image.convert("RGBA")
    mask = Image.new("L", rounded.size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle((0, 0, rounded.width - 1, rounded.height - 1), radius=radius, fill=255)
    rounded.putalpha(mask)
    return rounded


def largest_component(mask: np.ndarray) -> tuple[tuple[int, int, int, int], np.ndarray] | None:
    height, width = mask.shape
    visited = np.zeros(mask.shape, dtype=bool)
    best_count = 0
    best_bbox = None
    best_pixels: list[tuple[int, int]] = []

    for start_y, start_x in np.argwhere(mask):
        if visited[start_y, start_x]:
            continue

        queue = deque([(int(start_y), int(start_x))])
        visited[start_y, start_x] = True
        pixels: list[tuple[int, int]] = []
        count = 0
        min_x = max_x = int(start_x)
        min_y = max_y = int(start_y)

        while queue:
            y, x = queue.popleft()
            pixels.append((y, x))
            count += 1
            min_x = min(min_x, x)
            max_x = max(max_x, x)
            min_y = min(min_y, y)
            max_y = max(max_y, y)

            for next_y, next_x in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                if (
                    0 <= next_y < height
                    and 0 <= next_x < width
                    and mask[next_y, next_x]
                    and not visited[next_y, next_x]
                ):
                    visited[next_y, next_x] = True
                    queue.append((next_y, next_x))

        if count > best_count:
            best_count = count
            best_bbox = (min_x, min_y, max_x + 1, max_y + 1)
            best_pixels = pixels

    if best_bbox is None:
        return None

    component_mask = np.zeros(mask.shape, dtype=bool)
    for y, x in best_pixels:
        component_mask[y, x] = True
    return best_bbox, component_mask


def refine_bbox_by_projection(
    component_mask: np.ndarray,
    bbox: tuple[int, int, int, int],
    row_fraction: float = 0.42,
    col_fraction: float = 0.28,
) -> tuple[int, int, int, int]:
    left, top, right, bottom = bbox
    cropped = component_mask[top:bottom, left:right]
    row_counts = cropped.sum(axis=1)
    col_counts = cropped.sum(axis=0)

    valid_rows = np.flatnonzero(row_counts >= row_counts.max() * row_fraction)
    valid_cols = np.flatnonzero(col_counts >= col_counts.max() * col_fraction)
    if len(valid_rows) == 0 or len(valid_cols) == 0:
        return bbox

    return (
        left + int(valid_cols[0]),
        top + int(valid_rows[0]),
        left + int(valid_cols[-1]) + 1,
        top + int(valid_rows[-1]) + 1,
    )


def parse_search_box(text: str, image: Image.Image) -> tuple[int, int, int, int]:
    if text.strip().lower() == "full":
        return (0, 0, image.width, image.height)
    parts = [int(part.strip()) for part in text.split(",")]
    if len(parts) != 4:
        raise ValueError("--search-box must be 'full' or left,top,right,bottom")
    left, top, right, bottom = parts
    return (
        max(0, left),
        max(0, top),
        min(image.width, right),
        min(image.height, bottom),
    )


def detect_card_bbox(
    image: Image.Image,
    search_box: tuple[int, int, int, int],
    threshold: int,
    scale: float,
    padding: int,
    card_aspect: float,
) -> tuple[int, int, int, int]:
    search_image = image.crop(search_box)
    small_size = (max(1, int(search_image.width * scale)), max(1, int(search_image.height * scale)))
    small = search_image.resize(small_size, Image.Resampling.BILINEAR).convert("RGB")
    arr = np.asarray(small)

    brightness = arr.max(axis=2)
    saturation_like = arr.max(axis=2) - arr.min(axis=2)

    # Bright card surface and silver border should separate cleanly from the black photo backdrop.
    mask = (brightness > threshold) | ((brightness > threshold - 15) & (saturation_like > 18))
    mask_image = Image.fromarray((mask.astype(np.uint8) * 255), mode="L")
    mask_image = mask_image.filter(ImageFilter.MaxFilter(9)).filter(ImageFilter.MinFilter(9))
    mask = np.asarray(mask_image) > 0

    component = largest_component(mask)
    if component is None:
        raise RuntimeError("No card-like region detected.")
    bbox, component_mask = component
    bbox = refine_bbox_by_projection(component_mask, bbox)

    left, top, right, bottom = bbox
    inv_scale = 1 / scale
    offset_x, offset_y = search_box[:2]
    source_bbox = (
        max(0, offset_x + int(left * inv_scale) - padding),
        max(0, offset_y + int(top * inv_scale) - padding),
        min(image.width, offset_x + int(right * inv_scale) + padding),
        min(image.height, offset_y + int(bottom * inv_scale) + padding),
    )
    source_left, source_top, source_right, source_bottom = source_bbox
    detected_width = source_right - source_left
    expected_height = int(round(detected_width / card_aspect))
    aspect_bottom = min(image.height, source_top + expected_height)
    if source_bottom > aspect_bottom:
        source_bbox = (source_left, source_top, source_right, aspect_bottom)
    return source_bbox


def main() -> None:
    args = parse_args()
    output_dir = args.output_dir
    if output_dir is None:
        output_dir = timestamped_report_dir("card_crop_detector", args.report_label)
    elif not output_dir.is_absolute():
        output_dir = ROOT / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    image = ImageOps.exif_transpose(Image.open(args.input)).convert("RGB")
    search_box = parse_search_box(args.search_box, image)
    bbox = detect_card_bbox(image, search_box, args.threshold, args.scale, args.padding, args.card_aspect)

    crop = image.crop(bbox)
    stem = args.input.stem
    crop_path = output_dir / f"{stem}_detected_crop.png"
    rounded_crop_path = output_dir / f"{stem}_detected_crop_rounded.png"
    overlay_path = output_dir / f"{stem}_detected_overlay.jpg"
    mask_path = output_dir / f"{stem}_detected_mask.png"

    crop.save(crop_path)
    apply_rounded_mask(crop, args.corner_radius).save(rounded_crop_path)

    overlay = image.copy()
    draw = ImageDraw.Draw(overlay)
    draw.rectangle(search_box, outline=(80, 180, 255), width=10)
    draw.rectangle(bbox, outline=(255, 60, 60), width=14)
    overlay.thumbnail((1200, 1200), Image.Resampling.LANCZOS)
    overlay.save(overlay_path, quality=95)

    search_image = image.crop(search_box)
    small = search_image.resize((max(1, int(search_image.width * args.scale)), max(1, int(search_image.height * args.scale))))
    arr = np.asarray(small.convert("RGB"))
    brightness = arr.max(axis=2)
    saturation_like = arr.max(axis=2) - arr.min(axis=2)
    mask = (brightness > args.threshold) | ((brightness > args.threshold - 15) & (saturation_like > 18))
    mask_image = Image.fromarray((mask.astype(np.uint8) * 255), mode="L")
    mask_image = mask_image.filter(ImageFilter.MaxFilter(9)).filter(ImageFilter.MinFilter(9))
    mask_image.save(mask_path)

    print(f"Detected bbox: {bbox}")
    print(f"Crop: {crop_path}")
    print(f"Rounded crop: {rounded_crop_path}")
    print(f"Overlay: {overlay_path}")
    print(f"Mask: {mask_path}")


if __name__ == "__main__":
    main()
