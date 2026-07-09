from __future__ import annotations

import csv
import re
from pathlib import Path


SOURCE = Path(r"C:\Users\elste\Downloads\staged_evidence_rows.csv")
OUTPUT = Path(r"C:\Users\elste\Documents\IOOS Economic Impact\outputs\MARACOOS_staged_evidence_ready_to_upload.csv")
AUDIT_OUTPUT = Path(r"C:\Users\elste\Documents\IOOS Economic Impact\outputs\MARACOOS_staged_evidence_filter_audit.csv")

TEXT_FIELDS = [
    "region",
    "ioos_component",
    "decision_supported",
    "economic_pathway",
    "metric",
    "source",
    "claim_allowed",
    "ai_extraction_notes",
]

MARACOOS_TABLE_COLUMNS = [
    "row_id",
    "impact_domain",
    "ioos_component",
    "region",
    "ioos_region_code",
    "user_group",
    "decision_supported",
    "economic_pathway",
    "metric",
    "metric_year_or_dollar_year",
    "source",
    "source_url",
    "evidence_strength",
    "ioos_attribution_strength",
    "source_verification_needed",
    "limitations",
    "claim_allowed",
    "update_frequency",
    "ai_extraction_notes",
]

MARACOOS_PATTERN = re.compile(
    r"("
    r"MARACOOS|Mid[- ]Atlantic|Middle Atlantic|Cape Cod|Cape Hatteras|"
    r"Massachusetts|Rhode Island|Connecticut|New York|New Jersey|"
    r"Pennsylvania|Delaware|Maryland|Virginia|North Carolina|"
    r"District of Columbia|Washington,\s*DC|Washington,\s*D\.C\.|"
    r"Chesapeake|Delaware Bay|Delaware River|New York Bight|New York Harbor|"
    r"Hudson|Long Island|Block Island|Hampton Roads|Baltimore|"
    r"Virginia Beach|Assateague|Jersey Shelf|Hudson Canyon|"
    r"\bMA\b|\bRI\b|\bCT\b|\bNY\b|\bNJ\b|\bPA\b|\bDE\b|\bMD\b|\bVA\b|\bNC\b|\bDC\b"
    r")",
    re.IGNORECASE,
)

RATING_VALUES = {"Strong", "Medium", "Contextual", "Modeled", "Needs verification"}
VERIFICATION_VALUES = {"Yes", "No"}


def row_text(row: dict[str, str]) -> str:
    return " | ".join(row.get(field, "") or "" for field in TEXT_FIELDS)


def match_reason(row: dict[str, str]) -> str:
    code_parts = [
        part.strip()
        for part in (row.get("ioos_region_code") or "").split(";")
        if part.strip()
    ]
    if any(part.upper() == "MARACOOS" for part in code_parts):
        return "ioos_region_code"

    match = MARACOOS_PATTERN.search(row_text(row))
    if match:
        return match.group(0)

    return ""


def mark_maracoos(row: dict[str, str]) -> None:
    current = (row.get("ioos_region_code") or "").strip()
    if not current or current.lower() == "unknown":
        row["ioos_region_code"] = "MARACOOS"
        return

    parts = [part.strip() for part in current.split(";") if part.strip()]
    if not any(part.upper() == "MARACOOS" for part in parts):
        parts.append("MARACOOS")
    row["ioos_region_code"] = "; ".join(parts)


def main() -> int:
    with SOURCE.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)

    included: list[dict[str, str]] = []
    audit_rows: list[dict[str, str]] = []
    for row in rows:
        reason = match_reason(row)
        if not reason:
            continue
        output_row = dict(row)
        mark_maracoos(output_row)
        included.append(output_row)
        audit_rows.append(
            {
                "row_id": output_row.get("row_id", ""),
                "region": output_row.get("region", ""),
                "match_reason": reason,
                "source": output_row.get("source", ""),
            }
        )

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MARACOOS_TABLE_COLUMNS, lineterminator="\n")
        writer.writeheader()
        for row in included:
            writer.writerow({column: row.get(column, "") for column in MARACOOS_TABLE_COLUMNS})

    with AUDIT_OUTPUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["row_id", "region", "match_reason", "source"],
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(audit_rows)

    print(f"source_rows={len(rows)}")
    print(f"maracoos_rows={len(included)}")
    print(f"output={OUTPUT}")
    print(f"audit={AUDIT_OUTPUT}")

    row_ids = [row.get("row_id", "") for row in included]
    duplicate_row_ids = sorted({row_id for row_id in row_ids if row_ids.count(row_id) > 1})
    missing_required = [
        (row.get("row_id", ""), column)
        for row in included
        for column in MARACOOS_TABLE_COLUMNS
        if not (row.get(column) or "").strip()
    ]
    bad_evidence = [
        (row.get("row_id", ""), row.get("evidence_strength", ""))
        for row in included
        if row.get("evidence_strength", "") not in RATING_VALUES
    ]
    bad_attribution = [
        (row.get("row_id", ""), row.get("ioos_attribution_strength", ""))
        for row in included
        if row.get("ioos_attribution_strength", "") not in RATING_VALUES
    ]
    bad_verification = [
        (row.get("row_id", ""), row.get("source_verification_needed", ""))
        for row in included
        if row.get("source_verification_needed", "") not in VERIFICATION_VALUES
    ]
    print(f"duplicate_row_ids={duplicate_row_ids}")
    print(f"missing_required={missing_required[:20]}")
    print(f"bad_evidence={bad_evidence}")
    print(f"bad_attribution={bad_attribution}")
    print(f"bad_verification={bad_verification}")

    if duplicate_row_ids or missing_required or bad_evidence or bad_attribution or bad_verification:
        return 1

    print("included_rows:")
    for row in audit_rows:
        print(f"{row['row_id']}\t{row['region']}\t{row['match_reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
