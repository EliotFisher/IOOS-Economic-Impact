"""Streamlit dashboard for the IOOS Economic Impact Evidence Matrix."""

from __future__ import annotations

import csv
import io
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd
import streamlit as st


REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"
EVIDENCE_PATH = DATA_DIR / "evidence_matrix.csv"
SOURCE_PATH = DATA_DIR / "source_registry.csv"
REVIEW_PATH = DATA_DIR / "review_needed.csv"
STAGED_EVIDENCE_PATH = DATA_DIR / "staged_evidence.csv"
VALIDATOR_PATH = REPO_ROOT / "scripts" / "validate_matrix.py"

INTAKE_SCHEMA = [
    "row_id",
    "Impact domain",
    "IOOS component",
    "Region",
    "User group",
    "Decision supported",
    "Economic pathway",
    "Metric",
    "Metric year / dollar year",
    "Source",
    "Source URL",
    "Evidence strength",
    "IOOS attribution strength",
    "Source verification needed",
    "Limitations",
    "Claim allowed",
    "Update frequency",
    "AI extraction notes",
]

INTAKE_TO_EVIDENCE_COLUMNS = {
    "row_id": "row_id",
    "Impact domain": "impact_domain",
    "IOOS component": "ioos_component",
    "Region": "region",
    "User group": "user_group",
    "Decision supported": "decision_supported",
    "Economic pathway": "economic_pathway",
    "Metric": "metric",
    "Metric year / dollar year": "metric_year_or_dollar_year",
    "Source": "source_id",
    "Evidence strength": "evidence_strength",
    "IOOS attribution strength": "ioos_attribution_strength",
    "Source verification needed": "source_verification_needed",
    "Limitations": "limitations",
    "Claim allowed": "claim_allowed",
    "Update frequency": "update_frequency",
    "AI extraction notes": "ai_extraction_notes",
}

STAGED_DB_TO_INTAKE_COLUMNS = {
    "row_id": "row_id",
    "impact_domain": "Impact domain",
    "ioos_component": "IOOS component",
    "region": "Region",
    "user_group": "User group",
    "decision_supported": "Decision supported",
    "economic_pathway": "Economic pathway",
    "metric": "Metric",
    "metric_year_or_dollar_year": "Metric year / dollar year",
    "source": "Source",
    "source_url": "Source URL",
    "evidence_strength": "Evidence strength",
    "ioos_attribution_strength": "IOOS attribution strength",
    "source_verification_needed": "Source verification needed",
    "limitations": "Limitations",
    "claim_allowed": "Claim allowed",
    "update_frequency": "Update frequency",
    "ai_extraction_notes": "AI extraction notes",
}

INTAKE_TO_STAGED_DB_COLUMNS = {
    intake_column: db_column
    for db_column, intake_column in STAGED_DB_TO_INTAKE_COLUMNS.items()
}

PATH_TABLES = {
    EVIDENCE_PATH: "evidence_matrix",
    SOURCE_PATH: "source_registry",
    REVIEW_PATH: "review_needed",
    STAGED_EVIDENCE_PATH: "staged_evidence",
}

TABLE_DELETE_FILTERS = {
    "source_registry": ("source_id", "not.is.null"),
    "evidence_matrix": ("row_id", "not.is.null"),
    "review_needed": ("id", "not.is.null"),
    "staged_evidence": ("id", "not.is.null"),
}

TABLE_CONFLICT_KEYS = {
    "source_registry": "source_id",
    "evidence_matrix": "row_id",
}

TABLE_ORDER_COLUMNS = {
    "source_registry": "source_id",
    "evidence_matrix": "row_id",
    "review_needed": "id",
    "staged_evidence": "id",
}

INTAKE_REQUIRED_VALUES = [
    "Source",
    "Source URL",
    "Claim allowed",
    "Limitations",
    "Evidence strength",
    "IOOS attribution strength",
]

ALLOWED_RATINGS = {
    "Strong",
    "Medium",
    "Contextual",
    "Modeled",
    "Needs verification",
}

REQUIRED_ADD_FIELDS = [
    "impact_domain",
    "ioos_component",
    "source_id",
    "claim_allowed",
    "limitations",
    "evidence_strength",
    "ioos_attribution_strength",
]

REPORT_STATUS_ORDER = [
    "report-ready",
    "use-with-caution",
    "background-only",
    "needs-follow-up",
]

UPDATE_FREQUENCY_BUCKETS = {
    "Quarterly": [r"\bquarterly\b"],
    "Annual": [r"\bannual\b", r"\byearly\b"],
    "Real-time": [r"\breal[- ]?time\b"],
    "Periodic": [r"\bperiodic\b", r"\bongoing\b"],
    "Event-based": [r"\bevent[- ]?based\b"],
}

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

CONSERVATIVE_CLAIM_TERMS = [
    r"\bcan\b",
    r"\bcould\b",
    r"\bsupport",
    r"\bhelp",
    r"\bsuggest",
    r"\bestimated\b",
    r"\bmodeled\b",
    r"\bpotential\b",
    r"\bpending\b",
    r"\bwhere documented\b",
]


st.set_page_config(
    page_title="IOOS Economic Impact Evidence Matrix",
    page_icon=":bar_chart:",
    layout="wide",
)


def load_dotenv(path: Path) -> None:
    """Load simple KEY=VALUE pairs without adding a runtime dependency."""
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def get_secret(name: str) -> str:
    """Read Supabase settings from Streamlit secrets or the local environment."""
    try:
        secret_value = st.secrets.get(name, "")
    except Exception:
        secret_value = ""
    return str(secret_value or os.environ.get(name, "")).strip()


def supabase_settings() -> tuple[str, str]:
    load_dotenv(REPO_ROOT / ".env")
    return get_secret("SUPABASE_URL"), get_secret("SUPABASE_SERVICE_ROLE_KEY")


def supabase_enabled() -> bool:
    url, service_key = supabase_settings()
    return bool(url and service_key)


def supabase_request(
    method: str,
    table: str,
    query: dict[str, str] | None = None,
    body: object | None = None,
    prefer: str | None = None,
) -> object:
    """Call Supabase PostgREST using the service role key."""
    supabase_url, service_key = supabase_settings()
    if not supabase_url or not service_key:
        raise RuntimeError("Supabase settings are not configured.")

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
            text = response.read().decode("utf-8")
    except HTTPError as exc:
        message = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {table} failed with HTTP {exc.code}: {message}") from exc
    except URLError as exc:
        raise RuntimeError(f"{method} {table} failed: {exc.reason}") from exc

    if not text:
        return []
    return json.loads(text)


def map_supabase_rows_for_app(table: str, rows: list[dict[str, object]]) -> pd.DataFrame:
    """Convert Supabase rows back to the app's CSV-facing column names."""
    if table == "staged_evidence":
        mapped = [
            {
                intake_column: str(row.get(db_column, "") or "")
                for db_column, intake_column in STAGED_DB_TO_INTAKE_COLUMNS.items()
            }
            for row in rows
        ]
        return pd.DataFrame(mapped, columns=INTAKE_SCHEMA)

    if table == "review_needed":
        mapped = []
        for row in rows:
            mapped.append(
                {
                    "severity": str(row.get("severity", "") or ""),
                    "row_id": str(row.get("row_id", "") or ""),
                    "source_id": str(row.get("source_id", "") or ""),
                    "check": str(row.get("check_name", row.get("check", "")) or ""),
                    "message": str(row.get("message", "") or ""),
                }
            )
        return pd.DataFrame(mapped, columns=["severity", "row_id", "source_id", "check", "message"])

    records = []
    for row in rows:
        records.append(
            {
                key: str(value or "")
                for key, value in row.items()
                if key not in {"id", "updated_at"}
            }
        )
    return pd.DataFrame(records)


def map_rows_for_supabase(table: str, rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Convert app/CSV rows to Supabase table columns."""
    mapped_rows: list[dict[str, str]] = []
    for row in rows:
        if table == "staged_evidence":
            mapped_rows.append(
                {
                    db_column: normalize_text(row.get(intake_column))
                    for intake_column, db_column in INTAKE_TO_STAGED_DB_COLUMNS.items()
                }
            )
        elif table == "review_needed":
            mapped_rows.append(
                {
                    "severity": normalize_text(row.get("severity")),
                    "row_id": normalize_text(row.get("row_id")),
                    "source_id": normalize_text(row.get("source_id")),
                    "check_name": normalize_text(row.get("check", row.get("check_name"))),
                    "message": normalize_text(row.get("message")),
                }
            )
        else:
            mapped_rows.append({key: normalize_text(value) for key, value in row.items()})
    return mapped_rows


def load_supabase_table(table: str) -> pd.DataFrame:
    query = {"select": "*"}
    order_column = TABLE_ORDER_COLUMNS.get(table)
    if order_column:
        query["order"] = f"{order_column}.asc"
    rows = supabase_request("GET", table, query=query)
    return map_supabase_rows_for_app(table, rows if isinstance(rows, list) else [])


def replace_supabase_table(table: str, rows: list[dict[str, str]]) -> None:
    delete_column, delete_filter = TABLE_DELETE_FILTERS[table]
    supabase_request(
        "DELETE",
        table,
        query={delete_column: delete_filter},
        prefer="return=minimal",
    )
    append_supabase_rows(table, rows)


def append_supabase_rows(table: str, rows: list[dict[str, str]]) -> None:
    if not rows:
        return
    mapped_rows = map_rows_for_supabase(table, rows)
    conflict = TABLE_CONFLICT_KEYS.get(table)
    query = {"on_conflict": conflict} if conflict else None
    prefer = "resolution=merge-duplicates,return=minimal" if conflict else "return=minimal"
    supabase_request("POST", table, query=query, body=mapped_rows, prefer=prefer)


@st.cache_data(show_spinner=False)
def load_csv(path: Path) -> pd.DataFrame:
    """Load a CSV as strings so identifiers and matrix text are preserved."""
    table = PATH_TABLES.get(path)
    if table and supabase_enabled():
        return load_supabase_table(table)
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def clear_data_cache() -> None:
    """Refresh cached CSV reads after validation or row additions."""
    load_csv.clear()


def search_dataframe(df: pd.DataFrame, search_text: str) -> pd.DataFrame:
    """Return rows where any column contains the search text."""
    if df.empty or not search_text.strip():
        return df
    text = search_text.strip().lower()
    row_matches = df.astype(str).apply(
        lambda row: row.str.lower().str.contains(text, regex=False).any(),
        axis=1,
    )
    return df[row_matches]


def add_multiselect_filter(df: pd.DataFrame, column: str, label: str) -> pd.DataFrame:
    """Add a sidebar multiselect for a column when that column exists."""
    if column not in df.columns:
        return df
    options = sorted(value for value in df[column].dropna().unique() if str(value).strip())
    selected = st.sidebar.multiselect(label, options)
    if selected:
        return df[df[column].isin(selected)]
    return df


def add_status_filters(df: pd.DataFrame) -> pd.DataFrame:
    """Filter status/report-ready style fields when they are present."""
    status_columns = [
        column
        for column in df.columns
        if "status" in column.lower()
        or "report" in column.lower()
        or column == "source_verification_needed"
    ]
    for column in status_columns:
        df = add_multiselect_filter(df, column, column.replace("_", " ").title())
    return df


def render_filtered_table(df: pd.DataFrame, key_prefix: str) -> pd.DataFrame:
    """Render search, filters, table, and CSV download for a dataframe."""
    search_text = st.sidebar.text_input("Search", key=f"{key_prefix}_search")
    filtered = search_dataframe(df, search_text)

    filtered = add_multiselect_filter(filtered, "impact_domain", "Impact Domain")
    filtered = add_multiselect_filter(filtered, "evidence_strength", "Evidence Strength")
    filtered = add_multiselect_filter(
        filtered,
        "ioos_attribution_strength",
        "IOOS Attribution Strength",
    )
    filtered = add_multiselect_filter(filtered, "update_frequency", "Update Frequency")
    filtered = add_status_filters(filtered)

    st.caption(f"Showing {len(filtered):,} of {len(df):,} rows")
    st.dataframe(filtered, use_container_width=True, hide_index=True)
    st.download_button(
        "Download filtered CSV",
        filtered.to_csv(index=False).encode("utf-8"),
        file_name=f"{key_prefix}_filtered.csv",
        mime="text/csv",
    )
    return filtered


def intake_schema_csv_header() -> str:
    return ",".join(INTAKE_SCHEMA)


def research_prompt(topic: str) -> str:
    topic_text = topic.strip() or "[INSERT TOPIC]"
    return f"""You are generating candidate evidence rows for the IOOS Economic Evidence App.

Return only CSV rows using this exact schema:

{intake_schema_csv_header()}

Task:
Research the following IOOS economic impact topic:
{topic_text}

Rules:
- Use only real sources.
- Do not invent numbers, metrics, source titles, or URLs.
- If the evidence is qualitative, say so in the Metric field.
- If the source supports economic context but not IOOS-attributable benefit, set IOOS attribution strength to Contextual.
- If the claim is modeled, set Evidence strength to Modeled.
- If the source has not been manually checked, set Source verification needed to Yes.
- Use conservative claim language in Claim allowed.
- Include limitations for every row.
- Return CSV only."""


def source_prompt(source_text: str) -> str:
    source_body = source_text.strip() or "[PASTE SOURCE URL, TITLE, TEXT, ABSTRACT, OR REPORT EXCERPT]"
    return f"""You are extracting candidate rows for the IOOS Economic Evidence App.

Source:
{source_body}

Return only rows that fit this exact schema:

{intake_schema_csv_header()}

Rules:
- Extract only evidence actually supported by the source.
- Do not create a row if the source is too vague.
- Do not overstate IOOS attribution.
- If the source is not IOOS-specific, mark IOOS attribution strength as Contextual.
- If the source provides economic exposure but not avoided cost or benefit, say that in Limitations.
- Set Source verification needed to Yes unless the row has been manually checked.
- Write Claim allowed as a cautious sentence that COL could safely use.
- Return CSV only."""


def next_row_id(df: pd.DataFrame) -> str:
    """Suggest the next numeric row_id without changing existing rows."""
    if "row_id" not in df.columns or df.empty:
        return "1"
    numeric_ids = pd.to_numeric(df["row_id"], errors="coerce").dropna()
    if numeric_ids.empty:
        return ""
    return str(int(numeric_ids.max()) + 1)


def append_evidence_row(row: dict[str, str], columns: list[str]) -> None:
    """Append one row to the evidence store while preserving existing rows."""
    append_rows(EVIDENCE_PATH, [row], columns)


def write_csv(path: Path, rows: list[dict[str, str]], columns: list[str]) -> None:
    """Write rows with a fixed header and mirror supported tables to Supabase."""
    table = PATH_TABLES.get(path)
    if table and supabase_enabled():
        if table == "source_registry":
            append_supabase_rows(table, rows)
        else:
            replace_supabase_table(table, rows)

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def append_rows(path: Path, rows: list[dict[str, str]], columns: list[str]) -> None:
    """Append rows to local CSV and supported Supabase tables."""
    table = PATH_TABLES.get(path)
    if table and supabase_enabled():
        append_supabase_rows(table, rows)

    path.parent.mkdir(parents=True, exist_ok=True)
    file_exists = path.exists() and path.stat().st_size > 0
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        if not file_exists:
            writer.writeheader()
        writer.writerows(rows)


def normalize_intake_df(df: pd.DataFrame) -> pd.DataFrame:
    """Keep candidate rows on the exact intake contract and set review defaults."""
    normalized = df.copy()
    normalized.columns = [str(column).strip().lstrip("\ufeff") for column in normalized.columns]
    for column in INTAKE_SCHEMA:
        if column not in normalized.columns:
            normalized[column] = ""
    normalized = normalized[INTAKE_SCHEMA].fillna("").astype(str)
    normalized["Source verification needed"] = normalized["Source verification needed"].apply(
        lambda value: normalize_text(value) or "Yes"
    )
    return normalized


def validate_intake_df(df: pd.DataFrame) -> list[str]:
    """Validate AI candidate rows before they can enter staging or the matrix."""
    errors: list[str] = []
    columns = [str(column).strip().lstrip("\ufeff") for column in df.columns]
    missing_columns = [column for column in INTAKE_SCHEMA if column not in columns]
    extra_columns = [column for column in columns if column not in INTAKE_SCHEMA]

    if missing_columns:
        errors.append("Missing required columns: " + ", ".join(missing_columns))
    if extra_columns:
        errors.append("Unexpected columns: " + ", ".join(extra_columns))
    if errors:
        return errors

    normalized = normalize_intake_df(df)
    for index, row in normalized.iterrows():
        label = f"row {index + 1}"
        for column in INTAKE_REQUIRED_VALUES:
            if not normalize_text(row.get(column)):
                errors.append(f"{label} missing required value: {column}")
        for column in ["Evidence strength", "IOOS attribution strength"]:
            value = normalize_text(row.get(column))
            if value and value not in ALLOWED_RATINGS:
                errors.append(f"{label} has invalid {column}: {value}")
        verification = normalize_text(row.get("Source verification needed"))
        if verification not in {"Yes", "No"}:
            errors.append(f"{label} Source verification needed must be Yes or No")
    return errors


def slugify_source_id(value: str, existing_ids: set[str]) -> str:
    """Create a stable source_id from a staged Source value."""
    base = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "ai-intake-source"
    base = base[:60].strip("-") or "ai-intake-source"
    candidate = base
    suffix = 2
    while candidate in existing_ids:
        candidate = f"{base}-{suffix}"
        suffix += 1
    existing_ids.add(candidate)
    return candidate


def map_staged_row_to_evidence(row: dict[str, str], source_id: str, row_id: str) -> dict[str, str]:
    """Convert one exact-schema candidate row into the official matrix columns."""
    evidence_row = {
        evidence_column: normalize_text(row.get(intake_column))
        for intake_column, evidence_column in INTAKE_TO_EVIDENCE_COLUMNS.items()
    }
    evidence_row["row_id"] = row_id
    evidence_row["source_id"] = source_id
    return evidence_row


def source_lookup(source_df: pd.DataFrame) -> tuple[dict[tuple[str, str], str], set[str]]:
    """Build source matching helpers from the source registry."""
    lookup: dict[tuple[str, str], str] = {}
    existing_ids: set[str] = set()
    if source_df.empty:
        return lookup, existing_ids

    for _, source in source_df.iterrows():
        source_id = normalize_text(source.get("source_id"))
        if not source_id:
            continue
        existing_ids.add(source_id)
        key = (
            normalize_text(source.get("source_name")).lower(),
            normalize_text(source.get("source_url")).lower(),
        )
        lookup[key] = source_id
    return lookup, existing_ids


def accepted_rows_to_official(
    staged_rows: list[dict[str, str]],
    evidence_df: pd.DataFrame,
    source_df: pd.DataFrame,
) -> tuple[list[dict[str, str]], pd.DataFrame]:
    """Convert verified staged rows to official evidence rows and source records."""
    lookup, existing_ids = source_lookup(source_df)
    source_records = source_df.to_dict("records") if not source_df.empty else []
    source_row_index = {normalize_text(row.get("source_id")): row for row in source_records}
    used_row_ids = {normalize_text(row_id) for row_id in evidence_df.get("row_id", pd.Series(dtype=str))}
    next_id = int(next_row_id(evidence_df) or "1")
    evidence_rows: list[dict[str, str]] = []

    for row in staged_rows:
        source_name = normalize_text(row.get("Source"))
        source_url = normalize_text(row.get("Source URL"))
        key = (source_name.lower(), source_url.lower())
        source_id = lookup.get(key)
        if not source_id:
            source_id = slugify_source_id(source_name or source_url, existing_ids)
            lookup[key] = source_id
            source_record = {
                "source_id": source_id,
                "source_name": source_name,
                "source_url": source_url,
                "source_type": "AI intake",
                "verification_status": "Verified",
                "rows_supported": "",
                "notes": normalize_text(row.get("AI extraction notes")),
            }
            source_records.append(source_record)
            source_row_index[source_id] = source_record

        row_id = normalize_text(row.get("row_id"))
        if not row_id or row_id in used_row_ids:
            row_id = str(next_id)
            next_id += 1
        used_row_ids.add(row_id)

        evidence_rows.append(map_staged_row_to_evidence(row, source_id, row_id))
        source_record = source_row_index.get(source_id)
        if source_record is not None:
            supported = [
                value.strip()
                for value in normalize_text(source_record.get("rows_supported")).split(";")
                if value.strip()
            ]
            if row_id not in supported:
                supported.append(row_id)
            source_record["rows_supported"] = "; ".join(supported)

    source_columns = list(source_df.columns) if not source_df.empty else [
        "source_id",
        "source_name",
        "source_url",
        "source_type",
        "verification_status",
        "rows_supported",
        "notes",
    ]
    updated_sources = pd.DataFrame(source_records, columns=source_columns)
    return evidence_rows, updated_sources


def run_validation() -> subprocess.CompletedProcess[str]:
    """Run the Python validator using the current interpreter."""
    return subprocess.run(
        [sys.executable, str(VALIDATOR_PATH)],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def count_summary(df: pd.DataFrame, column: str) -> pd.DataFrame:
    """Build a readable count and percent table for one categorical column."""
    if df.empty or column not in df.columns:
        return pd.DataFrame(columns=["Category", "Rows", "Share"])

    counts = df[column].replace("", "Blank").value_counts().reset_index()
    counts.columns = ["Category", "Rows"]
    total = counts["Rows"].sum()
    counts["Share"] = (counts["Rows"] / total * 100) if total else 0
    return counts


def render_summary_table(df: pd.DataFrame, title: str) -> None:
    """Render category counts with bars that stay readable for long labels."""
    st.subheader(title)
    if df.empty:
        st.info("No data available.")
        return

    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Category": st.column_config.TextColumn(width="large"),
            "Rows": st.column_config.NumberColumn(width="small"),
            "Share": st.column_config.ProgressColumn(
                "Share",
                format="%.0f%%",
                min_value=0,
                max_value=100,
                width="medium",
            ),
        },
    )


def normalize_text(value: object) -> str:
    """Normalize text used by derived dashboard classifications."""
    return str(value or "").strip()


def row_warning_map(review_df: pd.DataFrame) -> dict[str, dict[str, object]]:
    """Group validator issues by evidence row_id for dashboard-only rollups."""
    if review_df.empty or "row_id" not in review_df.columns:
        return {}

    warning_map: dict[str, dict[str, object]] = {}
    for _, issue in review_df.iterrows():
        row_id = normalize_text(issue.get("row_id"))
        if not row_id:
            continue
        entry = warning_map.setdefault(
            row_id,
            {"checks": set(), "errors": 0, "warnings": 0, "messages": []},
        )
        severity = normalize_text(issue.get("severity")).lower()
        check = normalize_text(issue.get("check"))
        message = normalize_text(issue.get("message"))
        if check:
            entry["checks"].add(check)
        if message:
            entry["messages"].append(message)
        if severity == "error":
            entry["errors"] += 1
        elif severity == "warning":
            entry["warnings"] += 1
    return warning_map


def has_unclear_limitations(value: object) -> bool:
    """Flag limitations that are blank or too vague to support report drafting."""
    text = normalize_text(value).lower()
    return text in {"", "none", "n/a", "na", "not applicable", "unknown", "unclear", "tbd"}


def has_causal_language(value: object) -> bool:
    text = normalize_text(value)
    return any(re.search(pattern, text, re.I) for pattern in CAUSAL_TERMS)


def has_conservative_claim_language(row: pd.Series, checks: set[str]) -> bool:
    """Return True when claim text is cautious enough for shortlist review."""
    claim = normalize_text(row.get("claim_allowed"))
    if not claim:
        return False
    if "unsupported_causal_language" in checks:
        return False
    if not has_causal_language(claim):
        return True
    return any(re.search(pattern, claim, re.I) for pattern in CONSERVATIVE_CLAIM_TERMS)


def infer_report_status(row: pd.Series, checks: set[str], errors: int) -> str:
    """Infer report-readiness when the matrix has no explicit status column."""
    evidence = normalize_text(row.get("evidence_strength"))
    attribution = normalize_text(row.get("ioos_attribution_strength"))
    verification_needed = normalize_text(row.get("source_verification_needed")) == "Yes"
    claim_missing = not normalize_text(row.get("claim_allowed"))
    limitations_unclear = has_unclear_limitations(row.get("limitations"))

    if (
        errors
        or verification_needed
        or evidence == "Needs verification"
        or attribution == "Needs verification"
        or "source_verification_needed" in checks
        or "quantified_metric_needs_verification" in checks
        or "unsupported_causal_language" in checks
        or claim_missing
        or limitations_unclear
    ):
        return "needs-follow-up"

    if evidence == "Contextual" or attribution == "Contextual":
        return "background-only"

    if (
        evidence in {"Strong", "Medium"}
        and attribution in {"Strong", "Medium"}
        and not checks
    ):
        return "report-ready"

    return "use-with-caution"


def add_dashboard_fields(evidence_df: pd.DataFrame, review_df: pd.DataFrame) -> pd.DataFrame:
    """Add derived fields used only for dashboard display and filtering."""
    if evidence_df.empty:
        return evidence_df.copy()

    enriched = evidence_df.copy()
    warnings_by_row = row_warning_map(review_df)
    status_column = next((column for column in enriched.columns if column.lower() == "status"), None)

    statuses: list[str] = []
    warning_counts: list[int] = []
    error_counts: list[int] = []
    warning_checks: list[str] = []

    for _, row in enriched.iterrows():
        row_id = normalize_text(row.get("row_id"))
        issues = warnings_by_row.get(row_id, {})
        checks = set(issues.get("checks", set()))
        errors = int(issues.get("errors", 0))
        warnings = int(issues.get("warnings", 0))

        if status_column:
            status = normalize_text(row.get(status_column)) or "Unspecified"
        else:
            status = infer_report_status(row, checks, errors)

        statuses.append(status)
        warning_counts.append(warnings)
        error_counts.append(errors)
        warning_checks.append("; ".join(sorted(checks)))

    enriched["dashboard_status"] = statuses
    enriched["validation_warning_count"] = warning_counts
    enriched["validation_error_count"] = error_counts
    enriched["validation_warning_types"] = warning_checks
    return enriched


def status_counts_table(evidence_df: pd.DataFrame) -> pd.DataFrame:
    counts = evidence_df["dashboard_status"].value_counts().rename_axis("Status").reset_index(name="Rows")
    order = {status: index for index, status in enumerate(REPORT_STATUS_ORDER)}
    counts["_order"] = counts["Status"].map(lambda status: order.get(status, len(order)))
    return counts.sort_values(["_order", "Status"]).drop(columns="_order")


def render_status_cards(evidence_df: pd.DataFrame, source_df: pd.DataFrame, review_df: pd.DataFrame) -> None:
    status_counts = evidence_df["dashboard_status"].value_counts() if "dashboard_status" in evidence_df else {}
    unique_sources = evidence_df["source_id"].replace("", pd.NA).dropna().nunique() if "source_id" in evidence_df else len(source_df)
    errors = int((review_df["severity"].str.lower() == "error").sum()) if "severity" in review_df.columns else 0
    warnings = int((review_df["severity"].str.lower() == "warning").sum()) if "severity" in review_df.columns else 0

    cards = [
        ("Total evidence rows", len(evidence_df)),
        ("Unique sources", unique_sources),
        ("Report-ready rows", int(status_counts.get("report-ready", 0))),
        ("Use-with-caution rows", int(status_counts.get("use-with-caution", 0))),
        ("Background-only rows", int(status_counts.get("background-only", 0))),
        ("Needs-follow-up rows", int(status_counts.get("needs-follow-up", 0))),
        ("Validation errors", errors),
        ("Validation warnings", warnings),
    ]

    for row_start in range(0, len(cards), 4):
        columns = st.columns(4)
        for column, (label, value) in zip(columns, cards[row_start : row_start + 4]):
            column.metric(label, f"{value:,}")


def render_report_readiness_breakdown(evidence_df: pd.DataFrame) -> None:
    st.subheader("Report-Readiness Breakdown")
    if evidence_df.empty:
        st.info("No evidence rows available.")
        return

    counts = status_counts_table(evidence_df)
    chart_data = counts.set_index("Status")
    st.bar_chart(chart_data, y="Rows")
    st.dataframe(counts, use_container_width=True, hide_index=True)


def render_strength_crosstab(evidence_df: pd.DataFrame) -> None:
    st.subheader("Evidence Strength x IOOS Attribution Strength")
    required = {"evidence_strength", "ioos_attribution_strength"}
    if evidence_df.empty or not required.issubset(evidence_df.columns):
        st.info("Evidence and attribution strength columns are required for this table.")
        return

    crosstab = pd.crosstab(
        evidence_df["evidence_strength"].replace("", "Blank"),
        evidence_df["ioos_attribution_strength"].replace("", "Blank"),
        margins=True,
        margins_name="Total",
    )
    crosstab.index.name = "Evidence strength"
    st.dataframe(crosstab, use_container_width=True)


def domain_notes(domain_df: pd.DataFrame) -> str:
    notes: list[str] = []
    warning_count = int(domain_df["validation_warning_count"].sum()) if "validation_warning_count" in domain_df else 0
    if warning_count:
        notes.append("Warnings present")
    if "source_verification_needed" in domain_df and (domain_df["source_verification_needed"] == "Yes").any():
        notes.append("Source verification needed")
    if "ioos_attribution_strength" in domain_df and domain_df["ioos_attribution_strength"].isin(["Contextual", "Needs verification"]).any():
        notes.append("Weak or unverified attribution")
    if "evidence_strength" in domain_df and domain_df["evidence_strength"].isin(["Contextual", "Modeled", "Needs verification"]).any():
        notes.append("Contextual, modeled, or unverified evidence")
    return "; ".join(notes) if notes else "No current flags"


def render_domain_coverage(evidence_df: pd.DataFrame) -> None:
    st.subheader("Domain Coverage")
    if evidence_df.empty or "impact_domain" not in evidence_df.columns:
        st.info("No impact domain data available.")
        return

    rows: list[dict[str, object]] = []
    for domain, domain_df in evidence_df.groupby("impact_domain", dropna=False):
        rows.append(
            {
                "Impact domain": domain or "Blank",
                "total rows": len(domain_df),
                "strong evidence rows": int((domain_df["evidence_strength"] == "Strong").sum()) if "evidence_strength" in domain_df else 0,
                "strong IOOS attribution rows": int((domain_df["ioos_attribution_strength"] == "Strong").sum()) if "ioos_attribution_strength" in domain_df else 0,
                "report-ready rows": int((domain_df["dashboard_status"] == "report-ready").sum()),
                "warnings": int(domain_df["validation_warning_count"].sum()) if "validation_warning_count" in domain_df else 0,
                "notes": domain_notes(domain_df),
            }
        )

    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def render_review_workload(review_df: pd.DataFrame) -> None:
    st.subheader("Review Workload by Warning Type")
    if review_df.empty:
        st.success("No review workload is currently listed.")
        return
    if "check" not in review_df.columns:
        st.info("review_needed.csv does not include a check column.")
        return

    grouped = (
        review_df.assign(
            severity=review_df.get("severity", "").replace("", "unspecified"),
            row_id=review_df.get("row_id", "").astype(str),
        )
        .groupby(["check", "severity"], dropna=False)
        .agg(
            items=("check", "size"),
            affected_rows=("row_id", lambda values: ", ".join(sorted({value for value in values if value}))),
        )
        .reset_index()
        .sort_values(["severity", "items", "check"], ascending=[True, False, True])
    )
    st.dataframe(grouped, use_container_width=True, hide_index=True)


def display_columns(df: pd.DataFrame) -> list[str]:
    preferred = [
        "row_id",
        "dashboard_status",
        "impact_domain",
        "ioos_component",
        "region",
        "metric",
        "evidence_strength",
        "ioos_attribution_strength",
        "source_verification_needed",
        "claim_allowed",
        "limitations",
        "validation_warning_types",
    ]
    return [column for column in preferred if column in df.columns]


def render_best_candidates(evidence_df: pd.DataFrame) -> None:
    st.subheader("Best Candidate Rows for Final Report")
    if evidence_df.empty:
        st.info("No evidence rows available.")
        return

    mask = evidence_df["dashboard_status"] == "report-ready"
    for index, row in evidence_df.iterrows():
        checks = set(filter(None, normalize_text(row.get("validation_warning_types")).split("; ")))
        strong_or_medium = (
            normalize_text(row.get("evidence_strength")) in {"Strong", "Medium"}
            and normalize_text(row.get("ioos_attribution_strength")) in {"Strong", "Medium"}
        )
        if strong_or_medium and has_conservative_claim_language(row, checks):
            mask.loc[index] = True

    candidates = evidence_df[mask].copy()
    if candidates.empty:
        st.info("No rows currently meet the candidate criteria.")
        return
    st.dataframe(candidates[display_columns(candidates)], use_container_width=True, hide_index=True)


def follow_up_reasons(row: pd.Series) -> str:
    reasons: list[str] = []
    checks = set(filter(None, normalize_text(row.get("validation_warning_types")).split("; ")))
    attribution = normalize_text(row.get("ioos_attribution_strength"))

    if normalize_text(row.get("source_verification_needed")) == "Yes" or "source_verification_needed" in checks:
        reasons.append("source verification")
    if attribution in {"Contextual", "Needs verification"} or "weak_attribution" in checks:
        reasons.append("weak attribution")
    if "unsupported_causal_language" in checks:
        reasons.append("risky language")
    if has_unclear_limitations(row.get("limitations")):
        reasons.append("missing/unclear limitations")
    if normalize_text(row.get("evidence_strength")) == "Needs verification":
        reasons.append("evidence needs verification")
    return "; ".join(reasons)


def render_follow_up_rows(evidence_df: pd.DataFrame) -> None:
    st.subheader("Rows Needing Follow-Up")
    if evidence_df.empty:
        st.info("No evidence rows available.")
        return

    follow_up = evidence_df.copy()
    follow_up["follow_up_reasons"] = follow_up.apply(follow_up_reasons, axis=1)
    follow_up = follow_up[follow_up["follow_up_reasons"] != ""]
    if follow_up.empty:
        st.success("No rows currently match the follow-up criteria.")
        return

    columns = ["follow_up_reasons"] + display_columns(follow_up)
    st.dataframe(follow_up[columns], use_container_width=True, hide_index=True)


def render_update_frequency_breakdown(evidence_df: pd.DataFrame) -> None:
    st.subheader("Update-Frequency Breakdown")
    if evidence_df.empty or "update_frequency" not in evidence_df.columns:
        st.info("No update_frequency column available.")
        return

    rows: list[dict[str, object]] = []
    for bucket, patterns in UPDATE_FREQUENCY_BUCKETS.items():
        count = int(
            evidence_df["update_frequency"].apply(
                lambda value: any(re.search(pattern, normalize_text(value), re.I) for pattern in patterns)
            ).sum()
        )
        rows.append({"Update frequency": bucket, "Rows": count})

    st.caption("Rows can count in more than one category when the update_frequency field names multiple cadences.")
    frequency_df = pd.DataFrame(rows)
    st.bar_chart(frequency_df.set_index("Update frequency"), y="Rows")
    st.dataframe(frequency_df, use_container_width=True, hide_index=True)


def render_source_type_breakdown(source_df: pd.DataFrame) -> None:
    st.subheader("Source-Type Breakdown")
    if source_df.empty or "source_type" not in source_df.columns:
        st.info("No source_type data available.")
        return

    source_counts = count_summary(source_df, "source_type")
    st.dataframe(source_counts, use_container_width=True, hide_index=True)


def page_dashboard_summary(evidence_df: pd.DataFrame, source_df: pd.DataFrame, review_df: pd.DataFrame) -> None:
    st.title("Dashboard Summary")
    st.caption("At-a-glance status for evidence coverage, claim strength, and review workload.")

    evidence_dashboard_df = add_dashboard_fields(evidence_df, review_df)
    render_status_cards(evidence_dashboard_df, source_df, review_df)

    if not review_df.empty:
        review_errors = int((review_df["severity"].str.lower() == "error").sum()) if "severity" in review_df.columns else 0
        review_warnings = int((review_df["severity"].str.lower() == "warning").sum()) if "severity" in review_df.columns else 0
        st.warning(f"Validation review currently shows {review_errors} errors and {review_warnings} warnings.")
    else:
        st.success("No review items are currently listed.")

    top_left, top_right = st.columns([1.15, 1])
    with top_left:
        render_report_readiness_breakdown(evidence_dashboard_df)
    with top_right:
        render_strength_crosstab(evidence_dashboard_df)

    render_domain_coverage(evidence_dashboard_df)
    render_review_workload(review_df)
    render_best_candidates(evidence_dashboard_df)
    render_follow_up_rows(evidence_dashboard_df)

    bottom_left, bottom_right = st.columns(2)
    with bottom_left:
        render_update_frequency_breakdown(evidence_dashboard_df)
    with bottom_right:
        render_source_type_breakdown(source_df)


def page_evidence_matrix(evidence_df: pd.DataFrame) -> None:
    st.title("Evidence Matrix")
    if evidence_df.empty:
        st.warning(f"No evidence matrix found at {EVIDENCE_PATH}")
        return
    render_filtered_table(evidence_df, "evidence_matrix")


def page_review_needed(review_df: pd.DataFrame) -> None:
    st.title("Review Needed")
    if not REVIEW_PATH.exists():
        st.info("No review_needed.csv found. Run validation first.")
        return
    if review_df.empty:
        st.success("Validation review file exists and contains no flagged rows.")
        return
    st.dataframe(review_df, use_container_width=True, hide_index=True)
    st.download_button(
        "Download review_needed.csv",
        review_df.to_csv(index=False).encode("utf-8"),
        file_name="review_needed.csv",
        mime="text/csv",
    )


def page_source_registry(source_df: pd.DataFrame) -> None:
    st.title("Source Registry")
    if source_df.empty:
        st.warning(f"No source registry found at {SOURCE_PATH}")
        return

    search_text = st.sidebar.text_input("Search sources", key="source_search")
    filtered = search_dataframe(source_df, search_text)
    filtered = add_multiselect_filter(filtered, "source_type", "Source Type")
    filtered = add_multiselect_filter(filtered, "verification_status", "Verification Status")

    st.caption(f"Showing {len(filtered):,} of {len(source_df):,} sources")
    column_config = {}
    if "source_url" in filtered.columns:
        column_config["source_url"] = st.column_config.LinkColumn("Source URL")
    st.dataframe(
        filtered,
        use_container_width=True,
        hide_index=True,
        column_config=column_config,
    )


def render_intake_upload() -> None:
    st.subheader("Import Candidate CSV")
    if supabase_enabled():
        st.caption("Storage: Supabase live tables, with local CSV mirror.")
    else:
        st.caption("Storage: local CSV fallback. Add Supabase credentials to write live tables.")

    uploaded_file = st.file_uploader("Upload AI-generated candidate rows", type=["csv"])
    if uploaded_file is None:
        return

    file_bytes = uploaded_file.getvalue()

    try:
        candidate_df = pd.read_csv(io.BytesIO(file_bytes), dtype=str, keep_default_na=False)
    except Exception as exc:
        st.error(f"Could not read CSV: {exc}")
        return

    errors = validate_intake_df(candidate_df)
    if errors:
        st.error("Candidate CSV was not staged.")
        st.write("Fix these issues and upload again:")
        for error in errors:
            st.write(f"- {error}")
        return

    normalized = normalize_intake_df(candidate_df)
    storage_target = "Supabase staged_evidence" if supabase_enabled() else "local staged_evidence.csv"
    st.success(f"CSV passed intake validation with {len(normalized):,} candidate rows.")
    st.dataframe(normalized, use_container_width=True, hide_index=True)

    if st.button(f"Upload {len(normalized):,} rows to {storage_target}", type="primary"):
        try:
            append_rows(STAGED_EVIDENCE_PATH, normalized.to_dict("records"), INTAKE_SCHEMA)
        except Exception as exc:
            st.error(f"Upload failed: {exc}")
            return
        else:
            clear_data_cache()
            st.success(f"Uploaded {len(normalized):,} candidate rows to {storage_target}.")

    st.caption("Open Staged Evidence in the sidebar to review, edit, and accept verified rows.")


def page_evidence_intake() -> None:
    st.title("Evidence Intake")
    st.caption("Generate copy-ready prompts, then stage AI candidate rows before they become official evidence.")

    research_tab, source_tab, import_tab = st.tabs(["Research Topic", "Add Source", "Import CSV"])

    with research_tab:
        topic = st.text_area("Research question or topic", placeholder="Find 5 new evidence rows on HF radar and search and rescue.")
        prompt = research_prompt(topic)
        st.text_area("Copy-ready research prompt", value=prompt, height=420)
        st.download_button(
            "Download prompt",
            prompt.encode("utf-8"),
            file_name="ioos_research_to_row_prompt.txt",
            mime="text/plain",
        )

    with source_tab:
        source_text = st.text_area(
            "Source URL, title, report text, abstract, or excerpt",
            placeholder="Paste a NOAA report URL, title, abstract, or excerpt.",
            height=180,
        )
        prompt = source_prompt(source_text)
        st.text_area("Copy-ready source extraction prompt", value=prompt, height=420)
        st.download_button(
            "Download prompt",
            prompt.encode("utf-8"),
            file_name="ioos_source_to_row_prompt.txt",
            mime="text/plain",
        )

    with import_tab:
        st.code(intake_schema_csv_header(), language="text")
        render_intake_upload()


def page_staged_evidence(staged_df: pd.DataFrame, evidence_df: pd.DataFrame, source_df: pd.DataFrame) -> None:
    st.title("Staged Evidence")
    if not STAGED_EVIDENCE_PATH.exists():
        st.info("No staged evidence file exists yet. Use Evidence Intake to stage candidate rows.")
        return
    if staged_df.empty:
        st.success("No candidate rows are currently staged.")
        return

    staged_df = normalize_intake_df(staged_df)
    staged_df["review_status"] = staged_df["Source verification needed"].map(
        lambda value: "Verified / ready to accept" if value == "No" else "Needs verification"
    )

    edited = st.data_editor(
        staged_df,
        use_container_width=True,
        hide_index=True,
        num_rows="dynamic",
        column_config={
            "review_status": st.column_config.TextColumn(disabled=True),
        },
        disabled=["review_status"],
        key="staged_evidence_editor",
    )

    staged_to_save = edited.drop(columns=["review_status"], errors="ignore")
    save_errors = validate_intake_df(staged_to_save)
    left, right = st.columns([1, 1])

    with left:
        if st.button("Save staged edits"):
            if save_errors:
                st.error("Staged edits were not saved.")
                for error in save_errors:
                    st.write(f"- {error}")
            else:
                normalized = normalize_intake_df(staged_to_save)
                write_csv(STAGED_EVIDENCE_PATH, normalized.to_dict("records"), INTAKE_SCHEMA)
                clear_data_cache()
                st.success("Staged evidence saved.")
                st.rerun()

    with right:
        verified_mask = staged_to_save["Source verification needed"].map(normalize_text) == "No"
        verified_count = int(verified_mask.sum())
        if st.button(f"Accept {verified_count} verified rows", type="primary", disabled=verified_count == 0):
            if save_errors:
                st.error("Fix staged validation errors before accepting rows.")
                for error in save_errors:
                    st.write(f"- {error}")
                return

            normalized = normalize_intake_df(staged_to_save)
            verified_rows = normalized[verified_mask].to_dict("records")
            official_rows, updated_sources = accepted_rows_to_official(verified_rows, evidence_df, source_df)

            if official_rows:
                write_csv(SOURCE_PATH, updated_sources.to_dict("records"), list(updated_sources.columns))
                append_rows(EVIDENCE_PATH, official_rows, list(evidence_df.columns))

            remaining = normalized[~verified_mask]
            write_csv(STAGED_EVIDENCE_PATH, remaining.to_dict("records"), INTAKE_SCHEMA)
            clear_data_cache()
            st.success(f"Accepted {len(official_rows):,} rows into the official matrix.")
            st.rerun()

    st.download_button(
        "Download staged CSV",
        staged_to_save.to_csv(index=False).encode("utf-8"),
        file_name="staged_evidence.csv",
        mime="text/csv",
    )


def page_add_evidence_row(evidence_df: pd.DataFrame) -> None:
    st.title("Add Evidence Row")
    if evidence_df.empty:
        st.warning(f"No evidence matrix found at {EVIDENCE_PATH}")
        return

    st.caption("This form appends one new row and does not alter existing rows.")
    with st.form("add_evidence_row"):
        new_row: dict[str, str] = {}
        for column in evidence_df.columns:
            default_value = next_row_id(evidence_df) if column == "row_id" else ""
            if column in {
                "limitations",
                "claim_allowed",
                "ai_extraction_notes",
                "metric",
                "decision_supported",
                "economic_pathway",
            }:
                new_row[column] = st.text_area(column, value=default_value)
            else:
                new_row[column] = st.text_input(column, value=default_value)

        submitted = st.form_submit_button("Save row")

    if submitted:
        missing = [field for field in REQUIRED_ADD_FIELDS if not new_row.get(field, "").strip()]
        if missing:
            st.error("Please complete required fields: " + ", ".join(missing))
            return

        append_evidence_row(new_row, list(evidence_df.columns))
        clear_data_cache()
        st.success("Evidence row saved.")
        st.rerun()


def page_run_validation() -> None:
    st.title("Run Validation")
    st.write(f"Validator: `{VALIDATOR_PATH}`")
    if st.button("Run validation", type="primary"):
        result = run_validation()
        clear_data_cache()

        if result.returncode == 0:
            st.success("Validation completed successfully.")
        else:
            st.error("Validation completed with errors.")

        if result.stdout:
            st.code(result.stdout, language="text")
        if result.stderr:
            st.code(result.stderr, language="text")

        if REVIEW_PATH.exists():
            st.info(f"Refreshed `{REVIEW_PATH}`.")


def main() -> None:
    evidence_df = load_csv(EVIDENCE_PATH)
    source_df = load_csv(SOURCE_PATH)
    review_df = load_csv(REVIEW_PATH)
    staged_df = load_csv(STAGED_EVIDENCE_PATH)

    st.sidebar.title("IOOS Matrix")
    page = st.sidebar.radio(
        "Page",
        [
            "Dashboard Summary",
            "Evidence Matrix",
            "Evidence Intake",
            "Staged Evidence",
            "Review Needed",
            "Source Registry",
            "Add Evidence Row",
            "Run Validation",
        ],
    )

    if page == "Dashboard Summary":
        page_dashboard_summary(evidence_df, source_df, review_df)
    elif page == "Evidence Matrix":
        page_evidence_matrix(evidence_df)
    elif page == "Evidence Intake":
        page_evidence_intake()
    elif page == "Staged Evidence":
        page_staged_evidence(staged_df, evidence_df, source_df)
    elif page == "Review Needed":
        page_review_needed(review_df)
    elif page == "Source Registry":
        page_source_registry(source_df)
    elif page == "Add Evidence Row":
        page_add_evidence_row(evidence_df)
    elif page == "Run Validation":
        page_run_validation()


if __name__ == "__main__":
    main()
