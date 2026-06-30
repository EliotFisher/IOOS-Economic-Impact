"""Fill the IOOS congressional briefing HTML template from Supabase data."""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import os
from datetime import date
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = REPO_ROOT / "outputs" / "IOOS_Congressional_Briefing_Filled.html"


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def supabase_settings() -> tuple[str, str]:
    load_dotenv(REPO_ROOT / ".env")
    url = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
    key = (
        os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        or os.environ.get("SUPABASE_SERVICE_KEY", "").strip()
        or os.environ.get("SUPABASE_KEY", "").strip()
        or os.environ.get("SUPABASE_ANON_KEY", "").strip()
    )
    if not url or not key:
        raise RuntimeError("Set SUPABASE_URL and a Supabase API key in .env.")
    return url, key


def supabase_get(table: str, query: dict[str, str]) -> list[dict[str, object]]:
    supabase_url, key = supabase_settings()
    request_url = f"{supabase_url}/rest/v1/{table}?{urlencode(query)}"
    request = Request(
        request_url,
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "User-Agent": "CodexServerScript/1.0",
        },
    )
    try:
        with urlopen(request, timeout=60) as response:
            text = response.read().decode("utf-8")
    except HTTPError as exc:
        message = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Supabase read failed for {table}: HTTP {exc.code}: {message}") from exc
    except URLError as exc:
        raise RuntimeError(f"Supabase read failed for {table}: {exc.reason}") from exc

    rows = json.loads(text or "[]")
    if not isinstance(rows, list):
        raise RuntimeError(f"Expected a list from Supabase table {table}.")
    return rows


def load_live_data() -> tuple[list[dict[str, object]], dict[str, dict[str, object]]]:
    evidence = supabase_get("evidence_matrix", {"select": "*", "order": "row_id.asc"})
    sources = supabase_get("source_registry", {"select": "*", "order": "source_id.asc"})
    source_lookup = {str(row.get("source_id", "")): row for row in sources}
    return evidence, source_lookup


def read_csv_count(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open(newline="", encoding="utf-8") as handle:
        return sum(1 for _ in csv.DictReader(handle))


def build_brief(evidence: list[dict[str, object]], sources: dict[str, dict[str, object]]) -> str:
    """Use the Streamlit brief builder so script output matches the live app."""
    app_path = REPO_ROOT / "app" / "app.py"
    spec = importlib.util.spec_from_file_location("ioos_streamlit_app_for_brief", app_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load Streamlit app builder from {app_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    evidence_df = module.pd.DataFrame(evidence)
    source_df = module.pd.DataFrame(list(sources.values()))
    return module.build_congressional_briefing_html(
        evidence_df,
        source_df,
        "Congressional Staff",
        date.today(),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", type=Path, default=None, help="Deprecated; the brief now uses the app builder.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    evidence, sources = load_live_data()
    filled = build_brief(evidence, sources)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(filled, encoding="utf-8")

    local_rows = read_csv_count(REPO_ROOT / "data" / "evidence_matrix.csv")
    print(f"Wrote {args.output}")
    print(f"Supabase evidence rows: {len(evidence)}; source rows: {len(sources)}; local mirror rows: {local_rows}")


if __name__ == "__main__":
    main()
