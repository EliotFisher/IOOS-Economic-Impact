"""Validate the IOOS economic impact evidence matrix.

The validator checks the evidence matrix and source registry, then writes a
review file at data/review_needed.csv. It does not modify the source data.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EVIDENCE_PATH = REPO_ROOT / "data" / "evidence_matrix.csv"
DEFAULT_SOURCE_PATH = REPO_ROOT / "data" / "source_registry.csv"
DEFAULT_REVIEW_PATH = REPO_ROOT / "data" / "review_needed.csv"

ALLOWED_RATINGS = {
    "Strong",
    "Medium",
    "Contextual",
    "Modeled",
    "Needs verification",
}

REQUIRED_EVIDENCE_FIELDS = [
    "row_id",
    "impact_domain",
    "ioos_component",
    "region",
    "user_group",
    "decision_supported",
    "economic_pathway",
    "metric",
    "metric_year_or_dollar_year",
    "source_id",
    "evidence_strength",
    "ioos_attribution_strength",
    "source_verification_needed",
    "limitations",
    "claim_allowed",
    "update_frequency",
    "ai_extraction_notes",
]

REQUIRED_SOURCE_FIELDS = [
    "source_id",
    "source_name",
    "source_url",
    "source_type",
    "verification_status",
    "rows_supported",
    "notes",
]

CAUSAL_TERMS = [
    r"\bcaused?\b",
    r"\bcreated?\b",
    r"\battribut(?:e|ed|able|ion)\b",
    r"\bsaved?\b",
    r"\bprevent(?:ed|s|ing)?\b",
    r"\bavoided?\b",
    r"\breduced?\b",
    r"\bincreased?\b",
    r"\bprotected?\b",
    r"\bROI\b",
]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def is_blank(value: object) -> bool:
    return value is None or str(value).strip() == ""


def has_quantified_metric(row: dict[str, str]) -> bool:
    return bool(re.search(r"(?:\$|M\b|B\b|million|billion|%|\d)", row.get("metric", ""), re.I))


def has_unsupported_causal_language(row: dict[str, str]) -> bool:
    claim = row.get("claim_allowed", "")
    if not any(re.search(pattern, claim, re.I) for pattern in CAUSAL_TERMS):
        return False

    cautious = re.search(
        r"\b(can|could|support|supports|help|helps|suggest|suggests|estimated|modeled|potential|pending|where documented)\b",
        claim,
        re.I,
    )
    strong_enough = (
        row.get("evidence_strength") == "Strong"
        and row.get("ioos_attribution_strength") == "Strong"
    )
    verification_needed = row.get("source_verification_needed") == "Yes"

    return verification_needed or (not strong_enough and not cautious)


def add_issue(
    issues: list[dict[str, str]],
    severity: str,
    check: str,
    message: str,
    row_id: str = "",
    source_id: str = "",
) -> None:
    issues.append(
        {
            "severity": severity,
            "row_id": row_id,
            "source_id": source_id,
            "check": check,
            "message": message,
        }
    )


def validate(evidence_path: Path, source_path: Path) -> list[dict[str, str]]:
    impacts = read_csv(evidence_path)
    sources = read_csv(source_path)
    source_ids = {source.get("source_id", "") for source in sources}
    impact_row_ids = {row.get("row_id", "") for row in impacts}
    issues: list[dict[str, str]] = []

    for index, row in enumerate(impacts, start=1):
        row_id = row.get("row_id", "")
        label = f"row {row_id or index}"

        for field in REQUIRED_EVIDENCE_FIELDS:
            if field not in row or is_blank(row.get(field)):
                add_issue(issues, "error", "missing_field", f"{label} missing {field}", row_id=row_id)

        for field in ["evidence_strength", "ioos_attribution_strength"]:
            if row.get(field) not in ALLOWED_RATINGS:
                add_issue(
                    issues,
                    "error",
                    "invalid_rating",
                    f"{label} has invalid {field}: {row.get(field, '')}",
                    row_id=row_id,
                )

        if row.get("source_verification_needed") not in {"Yes", "No"}:
            add_issue(
                issues,
                "error",
                "invalid_verification_flag",
                f"{label} source_verification_needed must be Yes or No",
                row_id=row_id,
            )

        if row.get("source_id") not in source_ids:
            add_issue(
                issues,
                "error",
                "unknown_source",
                f"{label} references missing source_id {row.get('source_id', '')}",
                row_id=row_id,
                source_id=row.get("source_id", ""),
            )

        if row.get("ioos_attribution_strength") in {"Contextual", "Needs verification"}:
            add_issue(
                issues,
                "warning",
                "weak_attribution",
                f"{label} has weak IOOS attribution: {row.get('ioos_attribution_strength', '')}",
                row_id=row_id,
            )

        if row.get("source_verification_needed") == "Yes":
            add_issue(
                issues,
                "warning",
                "source_verification_needed",
                f"{label} should be checked against the original/full source before use",
                row_id=row_id,
            )

        if row.get("evidence_strength") == "Modeled":
            claim_context = f"{row.get('limitations', '')} {row.get('claim_allowed', '')}"
            if not re.search(r"\b(modeled|scenario|potential|estimated)\b", claim_context, re.I):
                add_issue(
                    issues,
                    "warning",
                    "modeled_claim_not_labeled",
                    f"{label} has Modeled evidence but claim/limitations do not clearly label it",
                    row_id=row_id,
                )

        if has_quantified_metric(row) and row.get("source_verification_needed") == "Yes":
            add_issue(
                issues,
                "warning",
                "quantified_metric_needs_verification",
                f"{label} has quantified metric values that need source verification",
                row_id=row_id,
            )

        if has_unsupported_causal_language(row):
            add_issue(
                issues,
                "warning",
                "unsupported_causal_language",
                f"{label} uses causal language that is stronger than the evidence/attribution flags support",
                row_id=row_id,
            )

    for index, source in enumerate(sources, start=1):
        source_id = source.get("source_id", "")
        label = f"source {source_id or index}"

        for field in REQUIRED_SOURCE_FIELDS:
            if field not in source or is_blank(source.get(field)):
                add_issue(
                    issues,
                    "error",
                    "missing_source_field",
                    f"{label} missing {field}",
                    source_id=source_id,
                )

        source_url = source.get("source_url", "")
        if source_url and not re.match(r"^https?://", source_url, re.I):
            add_issue(
                issues,
                "error",
                "invalid_source_url",
                f"{label} has invalid URL {source_url}",
                source_id=source_id,
            )

        for row_id in [part.strip() for part in source.get("rows_supported", "").split(";") if part.strip()]:
            if row_id not in impact_row_ids:
                add_issue(
                    issues,
                    "error",
                    "source_row_mismatch",
                    f"{label} references unknown impact row {row_id}",
                    source_id=source_id,
                )

    return issues


def write_review_file(path: Path, issues: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["severity", "row_id", "source_id", "check", "message"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(issues)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the IOOS evidence matrix.")
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE_PATH)
    parser.add_argument("--sources", type=Path, default=DEFAULT_SOURCE_PATH)
    parser.add_argument("--review", type=Path, default=DEFAULT_REVIEW_PATH)
    args = parser.parse_args()

    issues = validate(args.evidence, args.sources)
    write_review_file(args.review, issues)

    errors = [issue for issue in issues if issue["severity"] == "error"]
    warnings = [issue for issue in issues if issue["severity"] == "warning"]

    print(f"Validated {args.evidence}")
    print(f"Wrote {args.review}")
    print(f"Errors: {len(errors)}")
    print(f"Warnings: {len(warnings)}")

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
