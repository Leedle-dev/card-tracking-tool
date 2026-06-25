from pathlib import Path
import argparse
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageOps

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from card_tracker.report_paths import timestamped_report_dir
from test_card_crop_detector import DEFAULT_INPUT, detect_card_bbox, parse_search_box


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Test transparent card crop and stand suppression cleanup.")
    # Argument examples:
    #   python scripts/test_card_transparency_cleanup.py
    #   python scripts/test_card_transparency_cleanup.py --input "C:/Users/Lee/Pictures/ebay_card_business/GemPack5 - CBB5C/0805-07-Houndoom.jpg"
    #   python scripts/test_card_transparency_cleanup.py --stand-strength 0.55 --corner-radius 42
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="Card photo to process.")
    parser.add_argument("--output-dir", type=Path, help="Folder for debug outputs.")
    parser.add_argument(
        "--report-label",
        default="card_transparency_cleanup",
        help="Label for the generated timestamped report folder when --output-dir is omitted.",
    )
    parser.add_argument("--search-box", default="850,1200,2250,3400", help="Rough source image search box.")
    parser.add_argument("--threshold", type=int, default=55, help="Brightness threshold for crop detection.")
    parser.add_argument("--padding", type=int, default=8, help="Padding around detected card crop.")
    parser.add_argument("--scale", type=float, default=0.25, help="Detection scale factor.")
    parser.add_argument("--card-aspect", type=float, default=0.716, help="Physical card width divided by height.")
    parser.add_argument("--corner-radius", type=int, default=42, help="Rounded alpha mask corner radius.")
    parser.add_argument(
        "--stand-strength",
        type=float,
        default=0.45,
        help="How aggressively to remove gray/low-saturation stand pixels in the lower crop.",
    )
    return parser.parse_args()


def rounded_alpha(size: tuple[int, int], radius: int) -> Image.Image:
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius=radius, fill=255)
    return mask


def suppress_stand_alpha(crop: Image.Image, base_alpha: Image.Image, strength: float) -> tuple[Image.Image, Image.Image]:
    rgba = crop.convert("RGBA")
    rgb = np.asarray(rgba.convert("RGB"))
    alpha = np.asarray(base_alpha).copy()

    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    saturation = hsv[:, :, 1]
    value = hsv[:, :, 2]
    height, width = saturation.shape

    lower_region = np.zeros((height, width), dtype=bool)
    lower_region[int(height * 0.72) :, int(width * 0.20) : int(width * 0.80)] = True

    gray_plastic = (saturation < int(70 + 35 * strength)) & (value > 55) & (value < int(210 + 25 * strength))
    dark_edges = (saturation < int(55 + 25 * strength)) & (value < int(135 + 40 * strength))
    stand_mask = lower_region & (gray_plastic | dark_edges)

    kernel = np.ones((7, 7), np.uint8)
    stand_mask_u8 = (stand_mask.astype(np.uint8) * 255)
    stand_mask_u8 = cv2.morphologyEx(stand_mask_u8, cv2.MORPH_OPEN, kernel)
    stand_mask_u8 = cv2.dilate(stand_mask_u8, kernel, iterations=1)

    alpha[stand_mask_u8 > 0] = 0
    output = rgba.copy()
    output.putalpha(Image.fromarray(alpha, mode="L"))
    return output, Image.fromarray(stand_mask_u8, mode="L")


def main() -> None:
    args = parse_args()
    output_dir = args.output_dir
    if output_dir is None:
        output_dir = timestamped_report_dir("card_transparency_cleanup", args.report_label)
    elif not output_dir.is_absolute():
        output_dir = ROOT / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    image = ImageOps.exif_transpose(Image.open(args.input)).convert("RGB")
    search_box = parse_search_box(args.search_box, image)
    bbox = detect_card_bbox(image, search_box, args.threshold, args.scale, args.padding, args.card_aspect)
    crop = image.crop(bbox)
    base_alpha = rounded_alpha(crop.size, args.corner_radius)

    rounded = crop.convert("RGBA")
    rounded.putalpha(base_alpha)
    stand_cleaned, stand_mask = suppress_stand_alpha(crop, base_alpha, args.stand_strength)

    stem = args.input.stem
    rounded_path = output_dir / f"{stem}_transparent_rounded.png"
    stand_cleaned_path = output_dir / f"{stem}_transparent_stand_suppressed.png"
    stand_mask_path = output_dir / f"{stem}_stand_suppression_mask.png"

    rounded.save(rounded_path)
    stand_cleaned.save(stand_cleaned_path)
    stand_mask.save(stand_mask_path)

    print(f"Detected bbox: {bbox}")
    print(f"Rounded transparent: {rounded_path}")
    print(f"Stand suppressed transparent: {stand_cleaned_path}")
    print(f"Stand mask: {stand_mask_path}")


if __name__ == "__main__":
    main()
