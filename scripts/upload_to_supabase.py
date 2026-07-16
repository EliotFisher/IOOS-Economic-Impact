"""Upload local IOOS CSV data into Supabase via the PostgREST API.

Before running this script, create the tables with supabase/schema.sql and set:

  SUPABASE_URL=https://spfyejzxqornsfmoansk.supabase.co
  SUPABASE_SERVICE_ROLE_KEY=...
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"
DEFAULT_SUPABASE_URL = "https://spfyejzxqornsfmoansk.supabase.co"

CANDIDATE_COLUMNS = {
    "Date record created": "date_record_created",
    "Impact domain": "impact_domain",
    "IOOS component": "ioos_component",
    "Region": "region",
    "IOOS region code": "ioos_region_code",
    "User group": "user_group",
    "Decision supported": "decision_supported",
    "Economic pathway": "economic_pathway",
    "Metric": "metric",
    "Metric year / dollar year": "metric_year_or_dollar_year",
    "Source": "source",
    "Source URL": "source_url",
    "Evidence strength": "evidence_strength",
    "IOOS attribution strength": "ioos_attribution_strength",
    "Source verification needed": "source_verification_needed",
    "Limitations": "limitations",
    "Claim allowed": "claim_allowed",
    "Update frequency": "update_frequency",
    "AI extraction notes": "ai_extraction_notes",
    "Prompt used": "prompt_used",
}

CSV_TABLES = {
    "source_registry": {
        "path": DATA_DIR / "source_registry.csv",
        "delete_filter": ("source_id", "not.is.null"),
        "conflict": "source_id",
        "columns": None,
    },
    "evidence_matrix": {
        "path": DATA_DIR / "evidence_matrix.csv",
        "delete_filter": ("row_id", "not.is.null"),
        "conflict": "row_id",
        "columns": None,
    },
    "review_needed": {
        "path": DATA_DIR / "review_needed.csv",
        "delete_filter": ("id", "not.is.null"),
        "conflict": None,
        "columns": {
            "check": "check_name",
        },
    },
    "staged_evidence": {
        "path": DATA_DIR / "staged_evidence.csv",
        "delete_filter": ("id", "not.is.null"),
        "conflict": None,
        "columns": CANDIDATE_COLUMNS,
    },
    "best_sources": {
        "path": DATA_DIR / "best_sources.csv",
        "delete_filter": ("source_id", "not.is.null"),
        "conflict": "source_id",
        "columns": None,
    },
}

DELETE_ORDER = ["review_needed", "staged_evidence", "best_sources", "evidence_matrix", "source_registry"]
INSERT_ORDER = ["source_registry", "evidence_matrix", "review_needed", "staged_evidence", "best_sources"]


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def read_csv_rows(path: Path, columns: dict[str, str] | None = None) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not columns:
        return [{key: value or "" for key, value in row.items()} for row in rows]
    mapped_rows = []
    for row in rows:
        mapped_rows.append({columns.get(key, key): value or "" for key, value in row.items()})
    return mapped_rows


def api_request(
    supabase_url: str,
    service_key: str,
    method: str,
    table: str,
    query: dict[str, str] | None = None,
    body: object | None = None,
    prefer: str | None = None,
) -> tuple[int, str]:
    query_string = f"?{urlencode(query)}" if query else ""
    url = f"{supabase_url.rstrip('/')}/rest/v1/{table}{query_string}"
    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
    }
    payload = None
    if body is not None:
        payload = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if prefer:
        headers["Prefer"] = prefer

    request = Request(url, data=payload, headers=headers, method=method)
    try:
        with urlopen(request, timeout=60) as response:
            return response.status, response.read().decode("utf-8")
    except HTTPError as exc:
        message = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {table} failed with HTTP {exc.code}: {message}") from exc
    except URLError as exc:
        raise RuntimeError(f"{method} {table} failed: {exc.reason}") from exc


def run_validation() -> None:
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "validate_matrix.py")],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.stdout:
        print(result.stdout.strip())
    if result.stderr:
        print(result.stderr.strip(), file=sys.stderr)
    if result.returncode != 0:
        raise SystemExit("Validation failed; fix errors or rerun with --skip-validation.")


def delete_table(
    table: str,
    config: dict[str, object],
    supabase_url: str,
    service_key: str,
    dry_run: bool,
) -> None:
    if dry_run:
        return

    delete_column, delete_filter = config["delete_filter"]  # type: ignore[misc]
    api_request(
        supabase_url,
        service_key,
        "DELETE",
        table,
        query={delete_column: delete_filter},
        prefer="return=minimal",
    )


def insert_table(
    table: str,
    config: dict[str, object],
    supabase_url: str,
    service_key: str,
    dry_run: bool,
    chunk_size: int,
) -> None:
    rows = read_csv_rows(config["path"], config["columns"])  # type: ignore[arg-type]
    print(f"{table}: {len(rows)} row(s)")
    if dry_run:
        return

    if not rows:
        return

    conflict = config["conflict"]
    query = {"on_conflict": conflict} if conflict else None
    prefer = "resolution=merge-duplicates,return=minimal" if conflict else "return=minimal"
    for start in range(0, len(rows), chunk_size):
        chunk = rows[start : start + chunk_size]
        api_request(
            supabase_url,
            service_key,
            "POST",
            table,
            query=query,
            body=chunk,
            prefer=prefer,
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Upload IOOS CSV data to Supabase.")
    parser.add_argument("--url", default=os.environ.get("SUPABASE_URL", DEFAULT_SUPABASE_URL))
    parser.add_argument("--service-key", default=os.environ.get("SUPABASE_SERVICE_ROLE_KEY"))
    parser.add_argument("--tables", nargs="+", choices=CSV_TABLES.keys(), default=list(CSV_TABLES.keys()))
    parser.add_argument("--chunk-size", type=int, default=500)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-validation", action="store_true")
    args = parser.parse_args()

    load_dotenv(REPO_ROOT / ".env")

    service_key = args.service_key or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not service_key and not args.dry_run:
        raise SystemExit("Set SUPABASE_SERVICE_ROLE_KEY in .env or pass --service-key.")

    if not args.skip_validation:
        run_validation()

    selected_tables = set(args.tables)
    for table in DELETE_ORDER:
        if table in selected_tables:
            delete_table(table, CSV_TABLES[table], args.url, service_key or "", args.dry_run)

    for table in INSERT_ORDER:
        if table in selected_tables:
            insert_table(table, CSV_TABLES[table], args.url, service_key or "", args.dry_run, args.chunk_size)

    print("Supabase upload complete." if not args.dry_run else "Dry run complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
