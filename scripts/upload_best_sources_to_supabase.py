"""Upload planned briefing sources into the Supabase best_sources table.

Run supabase/schema.sql first so the best_sources table exists.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = REPO_ROOT / "data" / "best_sources.csv"
DEFAULT_SUPABASE_URL = "https://spfyejzxqornsfmoansk.supabase.co"
TABLE_NAME = "best_sources"


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [{key: value or "" for key, value in row.items()} for row in csv.DictReader(handle)]


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
        "User-Agent": "CodexServerScript/1.0",
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--url", default=os.environ.get("SUPABASE_URL", DEFAULT_SUPABASE_URL))
    parser.add_argument("--service-key", default=os.environ.get("SUPABASE_SERVICE_ROLE_KEY"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    load_dotenv(REPO_ROOT / ".env")
    service_key = args.service_key or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not service_key and not args.dry_run:
        raise SystemExit("Set SUPABASE_SERVICE_ROLE_KEY in .env or pass --service-key.")

    rows = read_rows(args.input)
    print(f"{TABLE_NAME}: {len(rows)} row(s)")
    if args.dry_run:
        return 0

    api_request(
        args.url,
        service_key or "",
        "DELETE",
        TABLE_NAME,
        query={"source_id": "not.is.null"},
        prefer="return=minimal",
    )
    if rows:
        api_request(
            args.url,
            service_key or "",
            "POST",
            TABLE_NAME,
            query={"on_conflict": "source_id"},
            body=rows,
            prefer="resolution=merge-duplicates,return=minimal",
        )
    print("best_sources upload complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
