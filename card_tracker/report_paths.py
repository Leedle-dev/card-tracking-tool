from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORTS_ROOT = PROJECT_ROOT / "reports"


def slugify_report_label(value: str | None, fallback: str = "report") -> str:
    label = re.sub(r"[^a-z0-9]+", "_", (value or fallback).lower()).strip("_")
    return label or fallback


def timestamped_report_dir(report_type: str, label: str | None = None) -> Path:
    """Create reports/<report_type>/<timestamp>_<label> and return it."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    folder_name = f"{timestamp}_{slugify_report_label(label, report_type)}"
    output_dir = REPORTS_ROOT / slugify_report_label(report_type) / folder_name
    suffix = 2
    while output_dir.exists():
        output_dir = REPORTS_ROOT / slugify_report_label(report_type) / f"{folder_name}_{suffix}"
        suffix += 1
    output_dir.mkdir(parents=True, exist_ok=False)
    return output_dir
