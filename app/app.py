"""Streamlit dashboard for the IOOS Economic Impact Evidence Matrix."""

from __future__ import annotations

import csv
import base64
import html as html_lib
import io
import json
import os
import re
import subprocess
import sys
from datetime import date
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components


REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "app"
DATA_DIR = REPO_ROOT / "data"
EVIDENCE_PATH = DATA_DIR / "evidence_matrix.csv"
SOURCE_PATH = DATA_DIR / "source_registry.csv"
REVIEW_PATH = DATA_DIR / "review_needed.csv"
STAGED_EVIDENCE_PATH = DATA_DIR / "staged_evidence.csv"
BEST_SOURCES_PATH = DATA_DIR / "best_sources.csv"
VALIDATOR_PATH = REPO_ROOT / "scripts" / "validate_matrix.py"
FILLED_BRIEFING_PATH = REPO_ROOT / "outputs" / "IOOS_Congressional_Briefing_Filled.html"
UCAR_LOGO_PATH = APP_DIR / "logo-ucar.avif"
COL_LOGO_PATH = APP_DIR / "col-logo.avif"

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
    BEST_SOURCES_PATH: "best_sources",
}

TABLE_DELETE_FILTERS = {
    "source_registry": ("source_id", "not.is.null"),
    "evidence_matrix": ("row_id", "not.is.null"),
    "review_needed": ("id", "not.is.null"),
    "staged_evidence": ("id", "not.is.null"),
    "best_sources": ("source_id", "not.is.null"),
}

TABLE_CONFLICT_KEYS = {
    "source_registry": "source_id",
    "evidence_matrix": "row_id",
    "best_sources": "source_id",
}

TABLE_ORDER_COLUMNS = {
    "source_registry": "source_id",
    "evidence_matrix": "row_id",
    "review_needed": "id",
    "staged_evidence": "id",
    "best_sources": "source_id",
}

SUPABASE_KEY_NAMES = [
    "SUPABASE_SERVICE_ROLE_KEY",
    "SUPABASE_SERVICE_KEY",
    "SUPABASE_KEY",
    "SUPABASE_ANON_KEY",
    "service_role_key",
    "service_key",
    "anon_key",
    "key",
]

SUPABASE_URL_NAMES = [
    "SUPABASE_URL",
    "supabase_url",
    "url",
]

SUPABASE_SECRET_SECTIONS = [
    ("supabase",),
    ("connections", "supabase"),
]

INTAKE_REQUIRED_VALUES = [
    "Source",
    "Source URL",
    "Claim allowed",
    "Limitations",
    "Evidence strength",
    "IOOS attribution strength",
]

ALLOWED_RATING_VALUES = [
    "Strong",
    "Medium",
    "Contextual",
    "Modeled",
    "Needs verification",
]
ALLOWED_RATINGS = set(ALLOWED_RATING_VALUES)

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

PROJECT_TIMELINE = [
    {
        "start": date(2026, 6, 1),
        "end": date(2026, 6, 29),
        "milestone": "Discovery and Prototype",
        "focus": "Explore AI workflows, build the first evidence workflow, identify economic data sources, and compare research tools.",
    },
    {
        "start": date(2026, 6, 30),
        "end": date(2026, 7, 8),
        "milestone": "Expansion and Scaling",
        "focus": "Vet information, expand the dataset, scale the framework for MARACOOS, and add imagery to summary materials.",
    },
    {
        "start": date(2026, 7, 8),
        "end": date(2026, 7, 14),
        "milestone": "Refinement",
        "focus": "Start finalizing the national report, expand regional evidence where useful, and document the workflow metadata.",
    },
    {
        "start": date(2026, 7, 14),
        "end": date(2026, 7, 21),
        "milestone": "Internal Review",
        "focus": "Identify IOOS, MIIS, and COL reviewers and begin the AI tools summary for COL.",
    },
    {
        "start": date(2026, 7, 21),
        "end": date(2026, 7, 28),
        "milestone": "Develop Materials",
        "focus": "Develop retreat materials and incorporate early reviewer comments.",
    },
    {
        "start": date(2026, 7, 28),
        "end": date(2026, 8, 4),
        "milestone": "Editing",
        "focus": "Continue incorporating comments and finalize report, workflow, and presentation materials.",
    },
    {
        "start": date(2026, 8, 4),
        "end": date(2026, 8, 11),
        "milestone": "Finalize",
        "focus": "Complete final polishing of the evidence matrix, workflow documentation, report, and retreat materials.",
    },
    {
        "start": date(2026, 8, 12),
        "end": date(2026, 8, 13),
        "milestone": "Boulder Retreat",
        "focus": "Present recommendations, facilitate discussion, gather staff feedback, and identify implementation priorities.",
    },
]

PROJECT_OBJECTIVES = [
    "Build a defensible national IOOS economic impact evidence base.",
    "Keep AI-generated rows staged until human verification clears them.",
    "Distinguish measured, modeled, contextual, and weak-attribution claims.",
    "Use MARACOOS as the first regional pilot for scaling the framework.",
    "Generate communication-ready report and briefing materials from vetted evidence.",
]

PROJECT_GOVERNANCE_RULES = [
    {
        "Area": "Staged evidence",
        "Rule": "Candidate rows stay outside the live matrix until Source verification needed is set to No.",
    },
    {
        "Area": "Claim language",
        "Rule": "Claims must stay conservative when evidence is modeled, contextual, or still under review.",
    },
    {
        "Area": "Source registry",
        "Rule": "Every official evidence row must point to an authoritative source_id with a working source URL.",
    },
    {
        "Area": "Review queue",
        "Rule": "Validation warnings and errors are treated as operator tasks before report-ready use.",
    },
    {
        "Area": "Briefing sources",
        "Rule": "The best_sources table is the curated shortlist for policy briefs and final report materials.",
    },
]

PROJECT_EVIDENCE_PRIORITIES = [
    {
        "Priority": "PORTS and maritime transportation",
        "Need": "Local case studies, port-safety benefits, draft optimization, and national scenario boundaries.",
    },
    {
        "Priority": "HF radar and search and rescue",
        "Need": "Operational SAROPS evidence, search-area reduction cases, and cautious public-safety value framing.",
    },
    {
        "Priority": "HAB forecasts and seafood decisions",
        "Need": "Forecast value, closure timing, avoided false alarms, and state or regional management evidence.",
    },
    {
        "Priority": "Ocean acidification and shellfish hatcheries",
        "Need": "Monitoring-to-decision pathways, hatchery adaptation evidence, and clear separation from sector exposure.",
    },
    {
        "Priority": "Ocean Enterprise and marine economy context",
        "Need": "Sector scale from Ocean Enterprise, BEA MESA, ENOW, NOEP, and other macroeconomic baselines.",
    },
    {
        "Priority": "MARACOOS regional pilot",
        "Need": "A repeatable regional case structure that can later extend to one or two additional regions.",
    },
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


def is_placeholder_secret(value: str) -> bool:
    lowered = value.lower()
    return not value or "replace" in lowered or "your-" in lowered


def get_nested_secret(section_path: tuple[str, ...], name: str) -> str:
    """Read a nested Streamlit secret without assuming a specific TOML shape."""
    try:
        current = st.secrets
        for section in section_path:
            current = current.get(section, {})
        value = current.get(name, "") if hasattr(current, "get") else ""
    except Exception:
        value = ""
    return str(value or "").strip()


def get_secret(name: str) -> str:
    """Read Supabase settings from Streamlit secrets or the local environment."""
    try:
        secret_value = st.secrets.get(name, "")
    except Exception:
        secret_value = ""
    return str(secret_value or os.environ.get(name, "")).strip()


def first_config_value(names: list[str]) -> str:
    """Find the first configured value across env, flat secrets, and nested secrets."""
    for name in names:
        value = get_secret(name)
        if value and not is_placeholder_secret(value):
            return value

    for section_path in SUPABASE_SECRET_SECTIONS:
        for name in names:
            value = get_nested_secret(section_path, name)
            if value and not is_placeholder_secret(value):
                return value

    return ""


def supabase_settings() -> tuple[str, str]:
    load_dotenv(REPO_ROOT / ".env")
    return first_config_value(SUPABASE_URL_NAMES), first_config_value(SUPABASE_KEY_NAMES)


def supabase_enabled() -> bool:
    url, service_key = supabase_settings()
    return bool(url and service_key)


def supabase_missing_settings() -> list[str]:
    url, service_key = supabase_settings()
    missing = []
    if not url:
        missing.append("Supabase URL")
    if not service_key:
        missing.append("Supabase API key")
    return missing


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
        "User-Agent": "IOOSStreamlitApp/1.0",
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


def allowed_ratings_text() -> str:
    return ", ".join(ALLOWED_RATING_VALUES)


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
- Evidence strength and IOOS attribution strength must be exactly one of: {allowed_ratings_text()}.
- Put rating explanations in Limitations or AI extraction notes, not in the rating fields.
- If the source supports economic context but not IOOS-attributable benefit, set IOOS attribution strength to Contextual.
- If the claim is modeled, set Evidence strength to Modeled.
- If the source has not been manually checked, set Source verification needed to Yes.
- Use conservative claim language in Claim allowed.
- Quote every CSV field that contains a comma, quote, or line break.
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
- Evidence strength and IOOS attribution strength must be exactly one of: {allowed_ratings_text()}.
- Put rating explanations in Limitations or AI extraction notes, not in the rating fields.
- If the source is not IOOS-specific, mark IOOS attribution strength as Contextual.
- If the source provides economic exposure but not avoided cost or benefit, say that in Limitations.
- Set Source verification needed to Yes unless the row has been manually checked.
- Write Claim allowed as a cautious sentence that COL could safely use.
- Quote every CSV field that contains a comma, quote, or line break.
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


def validate_intake_csv_shape(file_bytes: bytes) -> list[str]:
    """Catch malformed CSV records before pandas can reinterpret them as an index."""
    errors: list[str] = []
    try:
        csv_text = file_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        return ["CSV must be UTF-8 encoded."]

    try:
        reader = csv.reader(io.StringIO(csv_text))
        header = next(reader, None)
        if header is None:
            return ["CSV is empty."]

        expected_columns = len(header)
        for row_number, row in enumerate(reader, start=2):
            if not row or not any(normalize_text(value) for value in row):
                continue
            if len(row) != expected_columns:
                errors.append(
                    f"CSV row {row_number} has {len(row)} values, but the header has "
                    f"{expected_columns}. Quote fields that contain commas."
                )
    except csv.Error as exc:
        return [f"CSV could not be parsed: {exc}"]

    return errors


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
    for row_number, (_, row) in enumerate(normalized.iterrows(), start=1):
        label = f"row {row_number}"
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


def brief_escape(value: object) -> str:
    """Escape matrix text for the congressional briefing HTML preview."""
    return html_lib.escape(normalize_text(value), quote=False).replace("\u00ae", "&reg;")


def asset_data_uri(path: Path, mime_type: str) -> str:
    """Embed small static assets directly in generated HTML."""
    try:
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    except OSError:
        return ""
    return f"data:{mime_type};base64,{encoded}"


def evidence_row_by_id(evidence_df: pd.DataFrame, row_id: str) -> pd.Series | None:
    if evidence_df.empty or "row_id" not in evidence_df.columns:
        return None
    matches = evidence_df[evidence_df["row_id"].map(normalize_text) == row_id]
    if matches.empty:
        return None
    return matches.iloc[0]


def row_field(row: pd.Series | None, column: str, fallback: str = "") -> str:
    if row is None:
        return fallback
    value = normalize_text(row.get(column))
    return value or fallback


def congressional_briefing_context(
    evidence_df: pd.DataFrame,
    source_df: pd.DataFrame,
    prepared_for: str,
    prepared_date: date,
) -> dict[str, object]:
    """Collect the short text values used by both HTML and PDF brief exports."""
    rows = {
        row_id: evidence_row_by_id(evidence_df, row_id)
        for row_id in ["1", "5", "9", "14"]
    }
    prepared_for = normalize_text(prepared_for) or "Congressional Staff"
    date_label = prepared_date.strftime("%B %#d, %Y") if os.name == "nt" else prepared_date.strftime("%B %-d, %Y")

    return {
        "prepared_for": prepared_for,
        "date_label": date_label,
        "evidence_count": len(evidence_df),
        "source_count": len(source_df),
        "ocean_enterprise_metric": row_field(
            rows["14"],
            "metric",
            "Ocean Enterprise business, employment, revenue, and export metrics are tracked in the evidence matrix.",
        ),
        "tampa_metric": row_field(
            rows["1"],
            "metric",
            "Tampa Bay PORTS case-study benefits are tracked in the matrix.",
        ),
        "hab_forecast_claim": row_field(
            rows["5"],
            "claim_allowed",
            "HAB forecasts help managers focus testing and guide closure/advisory decisions.",
        ),
        "hf_radar_claim": row_field(
            rows["9"],
            "claim_allowed",
            "HF radar surface-current data support USCG search planning through SAROPS.",
        ),
    }


def build_congressional_briefing_html(
    evidence_df: pd.DataFrame,
    source_df: pd.DataFrame,
    prepared_for: str,
    prepared_date: date,
) -> str:
    """Build a concise print-friendly congressional brief from the current matrix rows."""
    context = congressional_briefing_context(evidence_df, source_df, prepared_for, prepared_date)
    prepared_for = str(context["prepared_for"])
    date_label = str(context["date_label"])
    evidence_count = int(context["evidence_count"])
    source_count = int(context["source_count"])
    ocean_enterprise_metric = str(context["ocean_enterprise_metric"])
    tampa_metric = str(context["tampa_metric"])
    hab_forecast_claim = str(context["hab_forecast_claim"])
    hf_radar_claim = str(context["hf_radar_claim"])
    ucar_logo_uri = asset_data_uri(UCAR_LOGO_PATH, "image/avif")
    col_logo_uri = asset_data_uri(COL_LOGO_PATH, "image/avif")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<style>
  :root {{
    --teal: #00A3B4;
    --teal-dark: #007785;
    --blue: #4A94B1;
    --gold: #F2A93B;
    --ink: #222;
    --gray: #5E6A71;
    --line: #D7E1E5;
    --panel: #EFF7F8;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    font-family: "Helvetica Neue", Arial, sans-serif;
    color: var(--ink);
    background: #888;
    margin: 0;
    padding: 20px 0 56px;
  }}
  .page {{
    width: 8.5in;
    min-height: 11in;
    margin: 0 auto 28px;
    background: #fff;
    padding: 0.5in 0.62in;
    box-shadow: 0 4px 18px rgba(0,0,0,0.25);
    font-size: 10.2pt;
    line-height: 1.32;
  }}
  .masthead {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    border-bottom: 3px solid var(--teal);
    padding-bottom: 9px;
    margin-bottom: 12px;
  }}
  .logos {{ display: flex; align-items: center; gap: 18px; }}
  .logos img.logo-ucar {{ height: 26px; width: auto; }}
  .logos img.logo-col {{ height: 46px; width: auto; }}
  .logos .divider {{ width: 1px; height: 36px; background: var(--line); }}
  .doc-label {{
    text-align: right;
    font-size: 8.5pt;
    color: var(--gray);
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }}
  .hero {{
    background: var(--teal);
    color: #fff;
    padding: 14px 16px;
    border-radius: 3px;
    margin-bottom: 12px;
  }}
  .hero .kicker {{
    font-size: 8.5pt;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: #DFF6F9;
    margin-bottom: 5px;
    font-weight: 700;
  }}
  .hero h1 {{ font-size: 23pt; line-height: 1.05; margin: 0 0 5px; }}
  .hero .subtitle {{ font-size: 11.2pt; margin: 0; color: #F2FCFD; }}
  .brief-meta {{
    display: flex;
    justify-content: space-between;
    color: var(--gray);
    font-size: 8.8pt;
    margin: -3px 0 10px;
  }}
  .metric-strip {{
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 8px;
    margin: 10px 0 12px;
  }}
  .metric {{
    border: 1px solid var(--line);
    border-top: 4px solid var(--gold);
    padding: 8px 9px;
    min-height: 58px;
  }}
  .metric .value {{ color: var(--teal-dark); font-weight: 800; font-size: 18pt; line-height: 1; }}
  .metric .label {{ color: var(--gray); font-size: 8.5pt; margin-top: 4px; }}
  h2.section {{
    font-size: 10.8pt;
    color: var(--teal-dark);
    border-bottom: 1.5px solid var(--teal);
    padding-bottom: 3px;
    margin: 12px 0 7px;
    font-weight: 800;
    letter-spacing: 0.02em;
    text-transform: uppercase;
  }}
  p {{ margin: 0 0 8px; }}
  .bottom-line {{
    background: var(--panel);
    border-left: 5px solid var(--teal);
    padding: 10px 13px;
    margin: 8px 0 12px;
    font-weight: 700;
    font-size: 11.2pt;
  }}
  .pillars {{
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 8px;
    margin-top: 8px;
  }}
  .pillar {{
    border: 1px solid var(--line);
    border-left: 4px solid var(--blue);
    padding: 8px 9px;
    min-height: 145px;
  }}
  .pillar h3 {{
    margin: 0 0 5px;
    color: var(--teal-dark);
    font-size: 10.2pt;
  }}
  .pillar p {{ font-size: 9.2pt; margin-bottom: 6px; }}
  .highlight {{ color: var(--teal-dark); font-weight: 800; }}
  .sector-grid {{
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 5px 18px;
    margin: 8px 0 12px;
    padding-left: 0;
    list-style: none;
  }}
  .sector-grid li {{
    border-bottom: 1px solid var(--line);
    padding-bottom: 4px;
  }}
  .ask-box {{
    background: var(--teal-dark);
    color: #fff;
    padding: 13px 15px;
    border-radius: 3px;
    margin-top: 12px;
    font-weight: 700;
  }}
  .ask-box .label {{
    color: #DFF6F9;
    font-size: 9pt;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    margin-bottom: 5px;
  }}
  .footnote {{ font-size: 8.1pt; color: var(--gray); font-style: italic; margin-top: 10px; }}
  .footer {{
    border-top: 1px solid var(--line);
    margin-top: 14px;
    padding-top: 7px;
    display: flex;
    justify-content: space-between;
    font-size: 8.2pt;
    color: var(--gray);
  }}
</style>
</head>
<body>
<div class="page">
  <div class="masthead">
    <div class="logos">
      <img class="logo-ucar" src="{ucar_logo_uri}" alt="UCAR">
      <div class="divider"></div>
      <img class="logo-col" src="{col_logo_uri}" alt="Center for Ocean Leadership">
    </div>
    <div class="doc-label">Congressional Brief</div>
  </div>

  <div class="hero">
    <div class="kicker">IOOS Reauthorization Brief</div>
    <h1>America&rsquo;s Ocean Intelligence System</h1>
    <p class="subtitle">The case for reauthorizing the Integrated Ocean Observing System (IOOS)</p>
  </div>
  <div class="brief-meta">
    <span>Prepared for: {brief_escape(prepared_for)}</span>
    <span>{brief_escape(date_label)}</span>
  </div>

  <div class="metric-strip">
    <div class="metric"><div class="value">5x</div><div class="label">Return on investment</div></div>
    <div class="metric"><div class="value">$400B</div><div class="label">U.S. ocean economy enabled</div></div>
    <div class="metric"><div class="value">325K</div><div class="label">Ocean Enterprise jobs supported</div></div>
    <div class="metric"><div class="value">$280M</div><div class="label">Requested over 5 years</div></div>
  </div>

  <div class="bottom-line">Bottom line: IOOS is proven national infrastructure. It turns ocean observations into safer ports, better storm decisions, stronger coastal economies, and private-sector growth.</div>

  <h2 class="section">What IOOS Is</h2>
  <p>IOOS is the United States&rsquo; national network of ocean sensors, buoys, radar systems, satellites, and data platforms that continuously monitors U.S. coastal waters, the Great Lakes, and ocean conditions.</p>
  <p>Think of it as the <b>interstate highway system for ocean data</b>: a federal investment that enables private-sector activity, operational decisions, and public safety outcomes that would not be possible without shared data infrastructure.</p>

  <h2 class="section">Why It Matters: Three Things Only IOOS Can Do</h2>
  <div class="pillars">
    <div class="pillar">
      <h3>1. Disaster Response</h3>
      <p>Storm surge kills more Americans than any other hurricane hazard. IOOS real-time coastal data powers forecasts that determine evacuation timing.</p>
      <p><b>Template example:</b> During Hurricane Sandy, IOOS data enabled 80 ships to safely evacuate Hampton Roads three days early, avoiding an estimated $28M in potential losses.</p>
    </div>
    <div class="pillar">
      <h3>2. Port Efficiency</h3>
      <p>IOOS water-level and current data helps port pilots optimize vessel drafts, reduce delays, and minimize costly lightering operations.</p>
      <p><b>Matrix evidence:</b> Tampa Bay PORTS&reg; benefits are {brief_escape(tampa_metric)}.</p>
    </div>
    <div class="pillar">
      <h3>3. Coastal Communities</h3>
      <p>IOOS powers HAB early-warning systems, supports fisheries decisions, and feeds search-and-rescue operations on every U.S. coastline.</p>
      <p><b>Matrix evidence:</b> {brief_escape(hab_forecast_claim)} {brief_escape(hf_radar_claim)}</p>
    </div>
  </div>
</div>

<div class="page">
  <div class="masthead">
    <div class="logos">
      <img class="logo-ucar" src="{ucar_logo_uri}" alt="UCAR">
      <div class="divider"></div>
      <img class="logo-col" src="{col_logo_uri}" alt="Center for Ocean Leadership">
    </div>
    <div class="doc-label">Congressional Brief</div>
  </div>

  <h2 class="section" style="margin-top:0;">The Economy IOOS Enables</h2>
  <p>IOOS is public data infrastructure for the ocean economy, including commercial shipping, offshore energy, recreational boating, coastal tourism, and seafood.</p>
  <p>The Ocean Enterprise survey reported <span class="highlight">{brief_escape(ocean_enterprise_metric)}</span>. Use this as sector context, not a claim that IOOS directly caused all revenue or jobs.</p>

  <ul class="sector-grid">
    <li>Commercial shipping and port operations</li>
    <li>Offshore energy development</li>
    <li>Recreational boating and coastal tourism</li>
    <li>Commercial and recreational fisheries</li>
    <li>Coastal hazard and emergency management</li>
    <li>U.S. Navy and Coast Guard operations</li>
    <li>Marine technology industry</li>
    <li>Shellfish and aquaculture businesses</li>
  </ul>

  <h2 class="section">The Legislative Moment</h2>
  <p>H.R. 2294 passed the House in March 2026 and companion S. 2126 is pending Senate action. Both bills authorize <b>$280 million over FY2026-2030</b>, or $56 million per year, consistent with current appropriations.</p>
  <p>This is not a new program. It is routine reauthorization of proven national infrastructure with documented economic and public safety value.</p>

  <h2 class="section">Staff Takeaway</h2>
  <p><b>Do not make this complicated:</b> IOOS is a modest federal investment that coastal states, ports, emergency managers, scientists, and ocean businesses already rely on. The policy choice is whether to keep that infrastructure stable.</p>

  <div class="ask-box">
    <div class="label">The Ask</div>
    Support Senate floor action on S. 2126 &nbsp; | &nbsp; Defend IOOS funding in CJS appropriations at or above current levels &nbsp; | &nbsp; Request a district-specific briefing on how IOOS serves coastal, port, fisheries, or emergency management stakeholders.
  </div>

  <div class="footnote">Source note: Built from the supplied Word brief template plus the current evidence matrix and source registry. Template legislative and non-matrix figures should be source-checked before external distribution.</div>

  <div class="footer">
    <span>IOOS Economic Impact Evidence Matrix | template-based congressional brief</span>
    <span>Sources: {source_count} | Evidence rows: {evidence_count}</span>
  </div>
</div>
</body>
</html>"""


def pdf_markup(value: object) -> str:
    """Escape text for ReportLab paragraphs and normalize glyphs for built-in fonts."""
    text = normalize_text(value)
    replacements = {
        "\u00ae": "(R)",
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2013": "-",
        "\u2014": "-",
        "\u00a0": " ",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return html_lib.escape(text, quote=False)


def pdf_logo_image(path: Path, height: float):
    """Convert AVIF logos to PNG-backed ReportLab images."""
    from PIL import Image as PILImage
    from reportlab.platypus import Image as ReportLabImage

    try:
        with PILImage.open(path) as image:
            if image.mode in {"RGBA", "LA"} or (image.mode == "P" and "transparency" in image.info):
                rgba = image.convert("RGBA")
                white = PILImage.new("RGBA", rgba.size, "WHITE")
                white.alpha_composite(rgba)
                converted = white.convert("RGB")
            else:
                converted = image.convert("RGB")

            png_bytes = io.BytesIO()
            converted.save(png_bytes, format="PNG")
            png_bytes.seek(0)
            width = height * (converted.width / converted.height)
            return ReportLabImage(png_bytes, width=width, height=height)
    except Exception:
        return None


def build_congressional_briefing_pdf(
    evidence_df: pd.DataFrame,
    source_df: pd.DataFrame,
    prepared_for: str,
    prepared_date: date,
) -> bytes:
    """Build a two-page PDF version of the congressional brief."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        HRFlowable,
        PageBreak,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    context = congressional_briefing_context(evidence_df, source_df, prepared_for, prepared_date)
    content_width = 7.26 * inch
    teal = colors.HexColor("#00A3B4")
    teal_dark = colors.HexColor("#007785")
    blue = colors.HexColor("#4A94B1")
    gold = colors.HexColor("#F2A93B")
    gray = colors.HexColor("#5E6A71")
    line = colors.HexColor("#D7E1E5")
    panel = colors.HexColor("#EFF7F8")

    styles = {
        "doc_label": ParagraphStyle(
            "DocLabel",
            fontName="Helvetica-Bold",
            fontSize=8.5,
            leading=10,
            textColor=gray,
            alignment=TA_RIGHT,
            uppercase=True,
        ),
        "hero_kicker": ParagraphStyle(
            "HeroKicker",
            fontName="Helvetica-Bold",
            fontSize=8.5,
            leading=10,
            textColor=colors.HexColor("#DFF6F9"),
            spaceAfter=3,
        ),
        "hero_h1": ParagraphStyle(
            "HeroH1",
            fontName="Helvetica-Bold",
            fontSize=23,
            leading=24,
            textColor=colors.white,
            spaceAfter=3,
        ),
        "hero_subtitle": ParagraphStyle(
            "HeroSubtitle",
            fontName="Helvetica",
            fontSize=11,
            leading=13,
            textColor=colors.HexColor("#F2FCFD"),
        ),
        "meta": ParagraphStyle(
            "Meta",
            fontName="Helvetica",
            fontSize=8.8,
            leading=10.5,
            textColor=gray,
        ),
        "metric_value": ParagraphStyle(
            "MetricValue",
            fontName="Helvetica-Bold",
            fontSize=18,
            leading=18,
            textColor=teal_dark,
            alignment=TA_CENTER,
        ),
        "metric_label": ParagraphStyle(
            "MetricLabel",
            fontName="Helvetica",
            fontSize=8.4,
            leading=10,
            textColor=gray,
            alignment=TA_CENTER,
        ),
        "body": ParagraphStyle(
            "Body",
            fontName="Helvetica",
            fontSize=9.8,
            leading=12.4,
            textColor=colors.HexColor("#222222"),
            spaceAfter=6,
        ),
        "body_small": ParagraphStyle(
            "BodySmall",
            fontName="Helvetica",
            fontSize=8.7,
            leading=10.8,
            textColor=colors.HexColor("#222222"),
            spaceAfter=5,
        ),
        "section": ParagraphStyle(
            "Section",
            fontName="Helvetica-Bold",
            fontSize=10.5,
            leading=12,
            textColor=teal_dark,
            spaceBefore=8,
            spaceAfter=2,
        ),
        "bottom_line": ParagraphStyle(
            "BottomLine",
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=13.5,
            textColor=colors.HexColor("#222222"),
        ),
        "pillar_heading": ParagraphStyle(
            "PillarHeading",
            fontName="Helvetica-Bold",
            fontSize=10,
            leading=12,
            textColor=teal_dark,
            spaceAfter=4,
        ),
        "ask_label": ParagraphStyle(
            "AskLabel",
            fontName="Helvetica-Bold",
            fontSize=8.5,
            leading=10,
            textColor=colors.HexColor("#DFF6F9"),
            spaceAfter=4,
        ),
        "ask": ParagraphStyle(
            "Ask",
            fontName="Helvetica-Bold",
            fontSize=10,
            leading=12.5,
            textColor=colors.white,
        ),
        "footnote": ParagraphStyle(
            "Footnote",
            fontName="Helvetica-Oblique",
            fontSize=8,
            leading=9.6,
            textColor=gray,
        ),
        "footer": ParagraphStyle(
            "Footer",
            fontName="Helvetica",
            fontSize=8,
            leading=9.5,
            textColor=gray,
        ),
    }

    def paragraph(text: object, style_name: str) -> Paragraph:
        return Paragraph(pdf_markup(text), styles[style_name])

    def rich_paragraph(markup: str, style_name: str) -> Paragraph:
        return Paragraph(markup, styles[style_name])

    def masthead() -> list[object]:
        ucar_logo = pdf_logo_image(UCAR_LOGO_PATH, 24)
        col_logo = pdf_logo_image(COL_LOGO_PATH, 44)
        logo_cells = []
        if ucar_logo is not None:
            logo_cells.append(ucar_logo)
        else:
            logo_cells.append(paragraph("UCAR", "body_small"))
        logo_cells.append("")
        if col_logo is not None:
            logo_cells.append(col_logo)
        else:
            logo_cells.append(paragraph("Center for Ocean Leadership", "body_small"))

        logo_table = Table([logo_cells], colWidths=[96, 14, 64])
        logo_table.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LINEBEFORE", (2, 0), (2, 0), 1, line),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ]
            )
        )
        head = Table(
            [[logo_table, paragraph("CONGRESSIONAL BRIEF", "doc_label")]],
            colWidths=[content_width - 150, 150],
        )
        head.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        return [
            head,
            HRFlowable(width="100%", thickness=3, color=teal, spaceBefore=0, spaceAfter=9),
        ]

    def section(title: str) -> list[object]:
        return [
            paragraph(title.upper(), "section"),
            HRFlowable(width="100%", thickness=1.2, color=teal, spaceBefore=0, spaceAfter=5),
        ]

    story: list[object] = []
    story.extend(masthead())

    hero = Table(
        [
            [
                [
                    rich_paragraph("IOOS REAUTHORIZATION BRIEF", "hero_kicker"),
                    rich_paragraph("America's Ocean Intelligence System", "hero_h1"),
                    rich_paragraph(
                        "The case for reauthorizing the Integrated Ocean Observing System (IOOS)",
                        "hero_subtitle",
                    ),
                ]
            ]
        ],
        colWidths=[content_width],
    )
    hero.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), teal),
                ("LEFTPADDING", (0, 0), (-1, -1), 14),
                ("RIGHTPADDING", (0, 0), (-1, -1), 14),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ]
        )
    )
    story.extend([hero, Spacer(1, 7)])

    meta = Table(
        [
            [
                paragraph(f"Prepared for: {context['prepared_for']}", "meta"),
                Paragraph(pdf_markup(context["date_label"]), styles["meta"].clone("MetaRight", alignment=TA_RIGHT)),
            ]
        ],
        colWidths=[content_width / 2, content_width / 2],
    )
    meta.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    story.extend([meta, Spacer(1, 7)])

    metric_cells = []
    for value, label in [
        ("5x", "Return on investment"),
        ("$400B", "U.S. ocean economy enabled"),
        ("325K", "Ocean Enterprise jobs supported"),
        ("$280M", "Requested over 5 years"),
    ]:
        metric_cells.append([rich_paragraph(value, "metric_value"), paragraph(label, "metric_label")])

    metric_table = Table([metric_cells], colWidths=[content_width / 4] * 4)
    metric_table.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.7, line),
                ("INNERGRID", (0, 0), (-1, -1), 0.7, line),
                ("LINEABOVE", (0, 0), (-1, -1), 3, gold),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    story.extend([metric_table, Spacer(1, 8)])

    bottom_line = Table(
        [[paragraph("Bottom line: IOOS is proven national infrastructure. It turns ocean observations into safer ports, better storm decisions, stronger coastal economies, and private-sector growth.", "bottom_line")]],
        colWidths=[content_width],
    )
    bottom_line.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), panel),
                ("LINEBEFORE", (0, 0), (0, 0), 5, teal),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.extend([bottom_line, Spacer(1, 3)])

    story.extend(section("What IOOS Is"))
    story.append(paragraph("IOOS is the United States' national network of ocean sensors, buoys, radar systems, satellites, and data platforms that continuously monitors U.S. coastal waters, the Great Lakes, and ocean conditions.", "body"))
    story.append(rich_paragraph("Think of it as the <b>interstate highway system for ocean data</b>: a federal investment that enables private-sector activity, operational decisions, and public safety outcomes that would not be possible without shared data infrastructure.", "body"))

    story.extend(section("Why It Matters: Three Things Only IOOS Can Do"))
    pillar_cells = [
        [
            rich_paragraph("1. Disaster Response", "pillar_heading"),
            paragraph("Storm surge kills more Americans than any other hurricane hazard. IOOS real-time coastal data powers forecasts that determine evacuation timing.", "body_small"),
            rich_paragraph("<b>Template example:</b> During Hurricane Sandy, IOOS data enabled 80 ships to safely evacuate Hampton Roads three days early, avoiding an estimated $28M in potential losses.", "body_small"),
        ],
        [
            rich_paragraph("2. Port Efficiency", "pillar_heading"),
            paragraph("IOOS water-level and current data helps port pilots optimize vessel drafts, reduce delays, and minimize costly lightering operations.", "body_small"),
            rich_paragraph(f"<b>Matrix evidence:</b> Tampa Bay PORTS(R) benefits are {pdf_markup(context['tampa_metric'])}.", "body_small"),
        ],
        [
            rich_paragraph("3. Coastal Communities", "pillar_heading"),
            paragraph("IOOS powers HAB early-warning systems, supports fisheries decisions, and feeds search-and-rescue operations on every U.S. coastline.", "body_small"),
            rich_paragraph(f"<b>Matrix evidence:</b> {pdf_markup(context['hab_forecast_claim'])} {pdf_markup(context['hf_radar_claim'])}", "body_small"),
        ],
    ]
    pillars = Table([pillar_cells], colWidths=[content_width / 3] * 3)
    pillars.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.7, line),
                ("INNERGRID", (0, 0), (-1, -1), 0.7, line),
                ("LINEBEFORE", (0, 0), (-1, -1), 3, blue),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.extend([pillars, PageBreak()])

    story.extend(masthead())
    story.extend(section("The Economy IOOS Enables"))
    story.append(paragraph("IOOS is public data infrastructure for the ocean economy, including commercial shipping, offshore energy, recreational boating, coastal tourism, and seafood.", "body"))
    story.append(rich_paragraph(f"The Ocean Enterprise survey reported <b><font color='#007785'>{pdf_markup(context['ocean_enterprise_metric'])}</font></b>. Use this as sector context, not a claim that IOOS directly caused all revenue or jobs.", "body"))

    sector_rows = [
        ["Commercial shipping and port operations", "Offshore energy development"],
        ["Recreational boating and coastal tourism", "Commercial and recreational fisheries"],
        ["Coastal hazard and emergency management", "U.S. Navy and Coast Guard operations"],
        ["Marine technology industry", "Shellfish and aquaculture businesses"],
    ]
    sector_table = Table(
        [[paragraph(left, "body_small"), paragraph(right, "body_small")] for left, right in sector_rows],
        colWidths=[content_width / 2, content_width / 2],
    )
    sector_table.setStyle(
        TableStyle(
            [
                ("LINEBELOW", (0, 0), (-1, -1), 0.6, line),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 14),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    story.extend([sector_table, Spacer(1, 6)])

    story.extend(section("The Legislative Moment"))
    story.append(rich_paragraph("H.R. 2294 passed the House in March 2026 and companion S. 2126 is pending Senate action. Both bills authorize <b>$280 million over FY2026-2030</b>, or $56 million per year, consistent with current appropriations.", "body"))
    story.append(paragraph("This is not a new program. It is routine reauthorization of proven national infrastructure with documented economic and public safety value.", "body"))

    story.extend(section("Staff Takeaway"))
    story.append(rich_paragraph("<b>Do not make this complicated:</b> IOOS is a modest federal investment that coastal states, ports, emergency managers, scientists, and ocean businesses already rely on. The policy choice is whether to keep that infrastructure stable.", "body"))

    ask_box = Table(
        [
            [
                [
                    rich_paragraph("THE ASK", "ask_label"),
                    paragraph(
                        "Support Senate floor action on S. 2126 | Defend IOOS funding in CJS appropriations at or above current levels | Request a district-specific briefing on how IOOS serves coastal, port, fisheries, or emergency management stakeholders.",
                        "ask",
                    ),
                ]
            ]
        ],
        colWidths=[content_width],
    )
    ask_box.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), teal_dark),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ]
        )
    )
    story.extend([ask_box, Spacer(1, 10)])
    story.append(paragraph("Source note: Built from the supplied Word brief template plus the current evidence matrix and source registry. Template legislative and non-matrix figures should be source-checked before external distribution.", "footnote"))
    story.extend([Spacer(1, 10), HRFlowable(width="100%", thickness=0.7, color=line, spaceBefore=0, spaceAfter=5)])
    footer = Table(
        [
            [
                paragraph("IOOS Economic Impact Evidence Matrix | template-based congressional brief", "footer"),
                Paragraph(
                    pdf_markup(f"Sources: {context['source_count']} | Evidence rows: {context['evidence_count']}"),
                    styles["footer"].clone("FooterRight", alignment=TA_RIGHT),
                ),
            ]
        ],
        colWidths=[content_width * 0.65, content_width * 0.35],
    )
    footer.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    story.append(footer)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=0.62 * inch,
        rightMargin=0.62 * inch,
        topMargin=0.5 * inch,
        bottomMargin=0.5 * inch,
    )
    doc.build(story)
    return buffer.getvalue()


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


def short_date(value: date) -> str:
    return f"{value.strftime('%b')} {value.day}"


def active_project_phase_index(today: date) -> int | None:
    active_indexes = [
        index
        for index, phase in enumerate(PROJECT_TIMELINE)
        if phase["start"] <= today <= phase["end"]
    ]
    if active_indexes:
        return active_indexes[-1]
    return None


def project_timeline_df(today: date) -> pd.DataFrame:
    active_index = active_project_phase_index(today)
    rows: list[dict[str, str]] = []
    for index, phase in enumerate(PROJECT_TIMELINE):
        if active_index is not None:
            status = "Active" if index == active_index else "Complete" if index < active_index else "Upcoming"
        elif today < PROJECT_TIMELINE[0]["start"]:
            status = "Upcoming"
        else:
            status = "Complete"

        rows.append(
            {
                "Dates": f"{short_date(phase['start'])} - {short_date(phase['end'])}",
                "Milestone": phase["milestone"],
                "Status": status,
                "Focus": phase["focus"],
            }
        )
    return pd.DataFrame(rows)


def project_table_status(
    evidence_df: pd.DataFrame,
    source_df: pd.DataFrame,
    review_df: pd.DataFrame,
    staged_df: pd.DataFrame,
    best_sources_df: pd.DataFrame,
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Table": "source_registry",
                "Rows": len(source_df),
                "Purpose": "Authoritative source metadata and URLs.",
            },
            {
                "Table": "evidence_matrix",
                "Rows": len(evidence_df),
                "Purpose": "Certified master matrix for report-ready claims.",
            },
            {
                "Table": "staged_evidence",
                "Rows": len(staged_df),
                "Purpose": "Temporary holding area for AI-generated candidate rows.",
            },
            {
                "Table": "review_needed",
                "Rows": len(review_df),
                "Purpose": "Validation issues and operator follow-up tasks.",
            },
            {
                "Table": "best_sources",
                "Rows": len(best_sources_df),
                "Purpose": "Curated shortlist for policy briefs and final materials.",
            },
        ]
    )


def page_project_roadmap(
    evidence_df: pd.DataFrame,
    source_df: pd.DataFrame,
    review_df: pd.DataFrame,
    staged_df: pd.DataFrame,
    best_sources_df: pd.DataFrame,
) -> None:
    st.title("Project Roadmap")
    st.caption("Proposal-aligned control center for the IOOS Matrix field project.")

    today = date.today()
    active_index = active_project_phase_index(today)
    if active_index is None:
        current_phase = "Complete" if today > PROJECT_TIMELINE[-1]["end"] else "Not started"
    else:
        current_phase = PROJECT_TIMELINE[active_index]["milestone"]

    metric_columns = st.columns(4)
    metric_columns[0].metric("Current phase", current_phase)
    metric_columns[1].metric("Core tables", "5")
    metric_columns[2].metric("Evidence rows", f"{len(evidence_df):,}")
    metric_columns[3].metric("Briefing sources", f"{len(best_sources_df):,}")

    objective_col, governance_col = st.columns([1, 1])
    with objective_col:
        st.subheader("Project Objectives")
        for objective in PROJECT_OBJECTIVES:
            st.write(f"- {objective}")

    with governance_col:
        st.subheader("Governance Rules")
        st.dataframe(
            pd.DataFrame(PROJECT_GOVERNANCE_RULES),
            use_container_width=True,
            hide_index=True,
        )

    st.subheader("Timeline")
    st.dataframe(
        project_timeline_df(today),
        use_container_width=True,
        hide_index=True,
        column_config={
            "Dates": st.column_config.TextColumn(width="small"),
            "Status": st.column_config.TextColumn(width="small"),
            "Focus": st.column_config.TextColumn(width="large"),
        },
    )

    table_col, priority_col = st.columns([0.9, 1.1])
    with table_col:
        st.subheader("Operational Tables")
        st.dataframe(
            project_table_status(evidence_df, source_df, review_df, staged_df, best_sources_df),
            use_container_width=True,
            hide_index=True,
            column_config={
                "Rows": st.column_config.NumberColumn(format="%d", width="small"),
                "Purpose": st.column_config.TextColumn(width="large"),
            },
        )

    with priority_col:
        st.subheader("Evidence Build Priorities")
        st.dataframe(
            pd.DataFrame(PROJECT_EVIDENCE_PRIORITIES),
            use_container_width=True,
            hide_index=True,
            column_config={
                "Priority": st.column_config.TextColumn(width="medium"),
                "Need": st.column_config.TextColumn(width="large"),
            },
        )


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


def page_best_sources(best_sources_df: pd.DataFrame) -> None:
    st.title("Best Sources")
    st.caption("Curated source shortlist for congressional briefs, final report sections, and retreat materials.")

    if best_sources_df.empty:
        st.warning(f"No best sources table found at {BEST_SOURCES_PATH}")
        return

    primary_count = (
        int((best_sources_df["priority_tier"].map(normalize_text) == "primary").sum())
        if "priority_tier" in best_sources_df.columns
        else 0
    )
    verified_count = (
        int((best_sources_df["source_verification_needed"].map(normalize_text) == "No").sum())
        if "source_verification_needed" in best_sources_df.columns
        else 0
    )
    planned_count = (
        int((best_sources_df["status"].map(normalize_text) == "planned").sum())
        if "status" in best_sources_df.columns
        else 0
    )

    metric_columns = st.columns(4)
    metric_columns[0].metric("Shortlist sources", f"{len(best_sources_df):,}")
    metric_columns[1].metric("Primary tier", f"{primary_count:,}")
    metric_columns[2].metric("Verified", f"{verified_count:,}")
    metric_columns[3].metric("Planned", f"{planned_count:,}")

    search_text = st.sidebar.text_input("Search best sources", key="best_sources_search")
    filtered = search_dataframe(best_sources_df, search_text)
    filtered = add_multiselect_filter(filtered, "priority_tier", "Priority Tier")
    filtered = add_multiselect_filter(filtered, "source_type", "Source Type")
    filtered = add_multiselect_filter(filtered, "source_verification_needed", "Verification Needed")
    filtered = add_multiselect_filter(filtered, "status", "Status")

    st.caption(f"Showing {len(filtered):,} of {len(best_sources_df):,} sources")
    column_config = {
        "source_url": st.column_config.LinkColumn("Source URL"),
        "briefing_role": st.column_config.TextColumn(width="large"),
        "key_metrics": st.column_config.TextColumn(width="large"),
        "recommended_claim_language": st.column_config.TextColumn(width="large"),
        "caveats": st.column_config.TextColumn(width="large"),
    }
    st.dataframe(
        filtered,
        use_container_width=True,
        hide_index=True,
        column_config={
            column: config for column, config in column_config.items() if column in filtered.columns
        },
    )
    st.download_button(
        "Download best_sources.csv",
        filtered.to_csv(index=False).encode("utf-8"),
        file_name="best_sources.csv",
        mime="text/csv",
    )


def page_congressional_briefing(evidence_df: pd.DataFrame, source_df: pd.DataFrame) -> None:
    st.title("Congressional Brief")
    st.caption("A punchy two-page IOOS reauthorization brief generated from the current evidence matrix and source registry.")

    if evidence_df.empty:
        st.warning("No evidence matrix rows are available.")
        return

    st.sidebar.subheader("Congressional Brief Draft")
    prepared_for = st.sidebar.text_input("Prepared for", value="Congressional Staff")
    prepared_date = st.sidebar.date_input("Brief date", value=date.today())

    briefing_html = build_congressional_briefing_html(
        evidence_df,
        source_df,
        prepared_for,
        prepared_date,
    )
    try:
        briefing_pdf = build_congressional_briefing_pdf(
            evidence_df,
            source_df,
            prepared_for,
            prepared_date,
        )
        pdf_error = ""
    except Exception as exc:
        briefing_pdf = b""
        pdf_error = str(exc)

    preview_tab, evidence_tab = st.tabs(["Preview", "Evidence Used"])

    with preview_tab:
        components.html(briefing_html, height=1700, scrolling=True)
        st.download_button(
            "Download live congressional brief HTML",
            briefing_html.encode("utf-8"),
            file_name="ioos_congressional_brief_live.html",
            mime="text/html",
        )
        if briefing_pdf:
            st.download_button(
                "Download live congressional brief PDF",
                briefing_pdf,
                file_name="ioos_congressional_brief_live.pdf",
                mime="application/pdf",
            )
        else:
            st.warning(f"PDF export is unavailable: {pdf_error}")

        if FILLED_BRIEFING_PATH.exists():
            st.download_button(
                "Download generated congressional brief draft",
                FILLED_BRIEFING_PATH.read_bytes(),
                file_name=FILLED_BRIEFING_PATH.name,
                mime="text/html",
            )

    with evidence_tab:
        briefing_row_ids = ["1", "5", "9", "14"]
        if "row_id" not in evidence_df.columns:
            st.info("The evidence matrix has no row_id column.")
            return

        rows_used = evidence_df[evidence_df["row_id"].map(normalize_text).isin(briefing_row_ids)].copy()
        if rows_used.empty:
            st.info("The brief row IDs are not present in the current matrix.")
            return

        display_columns = [
            column
            for column in [
                "row_id",
                "impact_domain",
                "region",
                "metric",
                "source_id",
                "evidence_strength",
                "ioos_attribution_strength",
                "source_verification_needed",
                "claim_allowed",
                "limitations",
            ]
            if column in rows_used.columns
        ]
        st.dataframe(rows_used[display_columns], use_container_width=True, hide_index=True)

        if not source_df.empty and "source_id" in source_df.columns:
            source_ids = {
                normalize_text(value)
                for value in rows_used.get("source_id", pd.Series(dtype=str)).tolist()
                if normalize_text(value)
            }
            sources_used = source_df[source_df["source_id"].map(normalize_text).isin(source_ids)]
            if not sources_used.empty:
                st.subheader("Sources")
                source_config = {}
                if "source_url" in sources_used.columns:
                    source_config["source_url"] = st.column_config.LinkColumn("Source URL")
                st.dataframe(
                    sources_used,
                    use_container_width=True,
                    hide_index=True,
                    column_config=source_config,
                )


def render_intake_upload() -> None:
    st.subheader("Import Candidate CSV")
    if supabase_enabled():
        st.caption("Storage: Supabase live tables, with local CSV mirror.")
    else:
        missing = "; ".join(supabase_missing_settings())
        st.warning(f"Supabase upload is not configured in this runtime. Missing: {missing}.")

    uploaded_file = st.file_uploader("Upload AI-generated candidate rows", type=["csv"])
    if uploaded_file is None:
        return

    file_bytes = uploaded_file.getvalue()
    csv_shape_errors = validate_intake_csv_shape(file_bytes)
    if csv_shape_errors:
        st.error("Candidate CSV was not staged.")
        st.write("Fix these issues and upload again:")
        for error in csv_shape_errors:
            st.write(f"- {error}")
        return

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
    st.success(f"CSV passed intake validation with {len(normalized):,} candidate rows.")
    st.dataframe(normalized, use_container_width=True, hide_index=True)

    if supabase_enabled():
        if st.button(f"Upload {len(normalized):,} rows to Supabase staged_evidence", type="primary"):
            try:
                append_rows(STAGED_EVIDENCE_PATH, normalized.to_dict("records"), INTAKE_SCHEMA)
            except Exception as exc:
                st.error(f"Supabase upload failed: {exc}")
                return
            else:
                clear_data_cache()
                st.success(f"Uploaded {len(normalized):,} candidate rows to Supabase staged_evidence.")
    else:
        st.button("Upload rows to Supabase staged_evidence", disabled=True, type="primary")
        if st.button(f"Save {len(normalized):,} rows to local staged_evidence.csv only"):
            try:
                append_rows(STAGED_EVIDENCE_PATH, normalized.to_dict("records"), INTAKE_SCHEMA)
            except Exception as exc:
                st.error(f"Local CSV save failed: {exc}")
                return
            else:
                clear_data_cache()
                st.success(f"Saved {len(normalized):,} candidate rows to local staged_evidence.csv.")

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
    best_sources_df = load_csv(BEST_SOURCES_PATH)

    st.sidebar.title("IOOS Matrix")
    page = st.sidebar.radio(
        "Page",
        [
            "Dashboard Summary",
            "Project Roadmap",
            "Evidence Matrix",
            "Congressional Brief",
            "Best Sources",
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
    elif page == "Project Roadmap":
        page_project_roadmap(evidence_df, source_df, review_df, staged_df, best_sources_df)
    elif page == "Evidence Matrix":
        page_evidence_matrix(evidence_df)
    elif page == "Congressional Brief":
        page_congressional_briefing(evidence_df, source_df)
    elif page == "Best Sources":
        page_best_sources(best_sources_df)
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
