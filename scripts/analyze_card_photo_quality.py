from pathlib import Path
import argparse
import csv
import statistics
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from card_tracker.report_paths import timestamped_report_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a photo QC report and contact sheets for card photos.")
    # Argument examples:
    #   "C:/Users/Lee/Pictures/ebay_card_business/GemPack5 - CBB5C"
    #   "C:/Users/Lee/Pictures/ebay_card_business/GemPack5 - CBB5C" --output-dir reports/photo_qc/YYYYMMDD_HHMMSS_gem_pack_5
    parser.add_argument("image_dir", help="Folder containing card listing photos.")
    parser.add_argument("--output-dir", help="Output folder for QC report files.")
    parser.add_argument(
        "--report-label",
        default="photo_qc",
        help="Label for the generated timestamped report folder when --output-dir is omitted.",
    )
    parser.add_argument("--sheet-cols", type=int, default=4, help="Contact sheet columns.")
    parser.add_argument("--thumb-width", type=int, default=360, help="Contact sheet thumbnail width.")
    return parser.parse_args()


def sharpness_score(gray: np.ndarray) -> float:
    gray = gray.astype(np.float32)
    dx = np.diff(gray, axis=1)
    dy = np.diff(gray, axis=0)
    return float(np.mean(dx * dx) + np.mean(dy * dy))


def image_metrics(path: Path) -> dict[str, object]:
    raw = Image.open(path)
    exif_orientation = raw.getexif().get(274)
    oriented = ImageOps.exif_transpose(raw).convert("RGB")
    arr = np.asarray(oriented)
    gray = arr.mean(axis=2)

    brightness = float(gray.mean())
    contrast = float(gray.std())
    sharpness = sharpness_score(gray)
    underexposed_pct = float((gray < 20).mean() * 100)
    overexposed_pct = float((gray > 245).mean() * 100)

    # Simple center-weighted estimate: card should occupy a meaningful but not full-frame area.
    h, w = gray.shape
    center = gray[int(h * 0.2): int(h * 0.85), int(w * 0.2): int(w * 0.85)]
    center_brightness = float(center.mean())

    flags = []
    if brightness < 50:
        flags.append("dark")
    if brightness > 190:
        flags.append("bright")
    if contrast < 35:
        flags.append("low_contrast")
    if sharpness < 17:
        flags.append("soft_focus")
    if overexposed_pct > 3:
        flags.append("glare_or_clipped_highlights")
    if underexposed_pct > 20:
        flags.append("heavy_shadow")

    return {
        "file": path.name,
        "raw_width": raw.width,
        "raw_height": raw.height,
        "display_width": oriented.width,
        "display_height": oriented.height,
        "exif_orientation": exif_orientation or "",
        "brightness": round(brightness, 2),
        "center_brightness": round(center_brightness, 2),
        "contrast": round(contrast, 2),
        "sharpness": round(sharpness, 2),
        "underexposed_pct": round(underexposed_pct, 2),
        "overexposed_pct": round(overexposed_pct, 2),
        "flags": ",".join(flags),
    }


def make_contact_sheets(paths: list[Path], metrics_by_file: dict[str, dict[str, object]], output_dir: Path, cols: int, thumb_width: int) -> None:
    font = ImageFont.load_default()
    label_height = 44
    gap = 14

    thumbs = []
    for path in paths:
        image = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
        ratio = thumb_width / image.width
        thumb_height = int(image.height * ratio)
        image = image.resize((thumb_width, thumb_height), Image.Resampling.LANCZOS)
        thumbs.append((path, image))

    rows_per_sheet = 5
    per_sheet = cols * rows_per_sheet

    for sheet_index in range(0, len(thumbs), per_sheet):
        chunk = thumbs[sheet_index: sheet_index + per_sheet]
        row_heights = []
        for row_start in range(0, len(chunk), cols):
            row_heights.append(max(image.height for _, image in chunk[row_start: row_start + cols]) + label_height)

        sheet_width = cols * thumb_width + (cols + 1) * gap
        sheet_height = sum(row_heights) + (len(row_heights) + 1) * gap
        sheet = Image.new("RGB", (sheet_width, sheet_height), "white")
        draw = ImageDraw.Draw(sheet)

        y = gap
        for row_number, row_start in enumerate(range(0, len(chunk), cols)):
            row = chunk[row_start: row_start + cols]
            x = gap
            for path, image in row:
                sheet.paste(image, (x, y))
                metrics = metrics_by_file[path.name]
                label = f"{path.stem}\nsharp {metrics['sharpness']} | over {metrics['overexposed_pct']}%"
                draw.multiline_text((x, y + image.height + 3), label, fill="black", font=font, spacing=2)
                x += thumb_width + gap
            y += row_heights[row_number] + gap

        sheet_number = sheet_index // per_sheet + 1
        sheet.save(output_dir / f"contact_sheet_{sheet_number:02d}.jpg", quality=92)


def main() -> None:
    args = parse_args()
    image_dir = Path(args.image_dir)
    output_dir = Path(args.output_dir) if args.output_dir else None
    if output_dir is None:
        output_dir = timestamped_report_dir("photo_qc", args.report_label)
    elif not output_dir.is_absolute():
        output_dir = ROOT / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    paths = sorted(
        [path for path in image_dir.iterdir() if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png"}],
        key=lambda path: path.name,
    )
    if not paths:
        raise SystemExit("No images found.")

    metrics = [image_metrics(path) for path in paths]
    metrics_by_file = {row["file"]: row for row in metrics}

    report_path = output_dir / "photo_quality_report.tsv"
    with report_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(metrics[0].keys()), delimiter="\t")
        writer.writeheader()
        writer.writerows(metrics)

    make_contact_sheets(paths, metrics_by_file, output_dir, args.sheet_cols, args.thumb_width)

    sharpness_values = [float(row["sharpness"]) for row in metrics]
    brightness_values = [float(row["brightness"]) for row in metrics]
    overexposed_values = [float(row["overexposed_pct"]) for row in metrics]
    flagged = [row for row in metrics if row["flags"]]

    print(f"Images analyzed: {len(metrics)}")
    print(f"Brightness mean/median: {statistics.mean(brightness_values):.2f} / {statistics.median(brightness_values):.2f}")
    print(f"Sharpness mean/median: {statistics.mean(sharpness_values):.2f} / {statistics.median(sharpness_values):.2f}")
    print(f"Overexposed pct mean/median: {statistics.mean(overexposed_values):.2f}% / {statistics.median(overexposed_values):.2f}%")
    print(f"Flagged images: {len(flagged)}")
    print(report_path)
    print(output_dir)


if __name__ == "__main__":
    main()
