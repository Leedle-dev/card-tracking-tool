from __future__ import annotations

from pathlib import Path
import argparse
import json
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from card_tracker.reporting import ReportBuilder, SheetSpec, WorkbookSpec, read_table_file


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a generic timestamped report from a JSON manifest.")
    # Argument examples:
    #   python scripts/build_report.py reports/report_manifest.example.json
    #   python scripts/build_report.py manifest.json --output-dir reports/manual_report/test_run
    parser.add_argument("manifest", type=Path, help="JSON manifest describing report files and sheets.")
    parser.add_argument("--output-dir", type=Path, help="Optional explicit report output directory.")
    return parser.parse_args()


def load_manifest(path: Path) -> dict[str, object]:
    manifest_path = path if path.is_absolute() else ROOT / path
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def rows_from_entry(entry: dict[str, object]) -> list[dict[str, object]]:
    if "rows" in entry:
        rows = entry["rows"]
        if not isinstance(rows, list):
            raise ValueError("rows must be a list of objects.")
        return [dict(row) for row in rows if isinstance(row, dict)]

    source = entry.get("source")
    if source:
        delimiter = entry.get("delimiter")
        return read_table_file(Path(str(source)), delimiter=str(delimiter) if delimiter else None)

    return []


def sheet_from_entry(entry: dict[str, object]) -> SheetSpec:
    rows = rows_from_entry(entry)
    return SheetSpec(
        name=str(entry["name"]),
        rows=rows,
        fieldnames=list(entry["fieldnames"]) if entry.get("fieldnames") else None,
        title=str(entry["title"]) if entry.get("title") else None,
        freeze_panes=str(entry["freeze_panes"]) if entry.get("freeze_panes") else "A2",
        auto_filter=bool(entry.get("auto_filter", True)),
        table_name=str(entry["table_name"]) if entry.get("table_name") else None,
        table_style=str(entry.get("table_style", "TableStyleMedium2")),
        header_fill=str(entry.get("header_fill", "1F2937")),
        header_font_color=str(entry.get("header_font_color", "FFFFFF")),
        column_widths=dict(entry.get("column_widths", {})),
        column_fills=dict(entry.get("column_fills", {})),
        number_formats=dict(entry.get("number_formats", {})),
        hidden_columns=list(entry.get("hidden_columns", [])),
        currency_columns=list(entry.get("currency_columns", [])),
        percent_columns=list(entry.get("percent_columns", [])),
        integer_columns=list(entry.get("integer_columns", [])),
    )


def main() -> None:
    args = parse_args()
    manifest = load_manifest(args.manifest)
    report = ReportBuilder(
        report_type=str(manifest.get("report_type", "manual_report")),
        label=str(manifest.get("label", "report")),
        output_dir=args.output_dir,
        metadata=manifest.get("metadata") if isinstance(manifest.get("metadata"), dict) else None,
    )

    for file_entry in manifest.get("files", []):
        if not isinstance(file_entry, dict):
            raise ValueError("Each files[] entry must be an object.")
        kind = str(file_entry.get("kind", "")).lower()
        filename = str(file_entry["filename"])
        key = str(file_entry["key"]) if file_entry.get("key") else None

        if kind == "tsv":
            report.write_tsv(filename, rows_from_entry(file_entry), fieldnames=file_entry.get("fieldnames"), key=key)
        elif kind == "csv":
            report.write_csv(filename, rows_from_entry(file_entry), fieldnames=file_entry.get("fieldnames"), key=key)
        elif kind == "json":
            report.write_json(filename, file_entry.get("data", {}), key=key, raw=bool(file_entry.get("raw", False)))
        elif kind == "text":
            report.write_text(filename, str(file_entry.get("text", "")), key=key)
        elif kind == "xlsx":
            sheets = [sheet_from_entry(sheet) for sheet in file_entry.get("sheets", []) if isinstance(sheet, dict)]
            report.write_workbook(WorkbookSpec(filename=filename, sheets=sheets), key=key)
        else:
            raise ValueError(f"Unsupported file kind: {kind!r}")

    metadata_path = report.write_metadata()
    print(report.output_dir)
    print(metadata_path)


if __name__ == "__main__":
    main()
