"""Streamlit dashboard for the IOOS Economic Impact Evidence Matrix."""

from __future__ import annotations

import csv
import subprocess
import sys
from pathlib import Path

import pandas as pd
import streamlit as st


REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"
EVIDENCE_PATH = DATA_DIR / "evidence_matrix.csv"
SOURCE_PATH = DATA_DIR / "source_registry.csv"
REVIEW_PATH = DATA_DIR / "review_needed.csv"
VALIDATOR_PATH = REPO_ROOT / "scripts" / "validate_matrix.py"

REQUIRED_ADD_FIELDS = [
    "impact_domain",
    "ioos_component",
    "source_id",
    "claim_allowed",
    "limitations",
    "evidence_strength",
    "ioos_attribution_strength",
]


st.set_page_config(
    page_title="IOOS Economic Impact Evidence Matrix",
    page_icon=":bar_chart:",
    layout="wide",
)


@st.cache_data(show_spinner=False)
def load_csv(path: Path) -> pd.DataFrame:
    """Load a CSV as strings so identifiers and matrix text are preserved."""
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


def next_row_id(df: pd.DataFrame) -> str:
    """Suggest the next numeric row_id without changing existing rows."""
    if "row_id" not in df.columns or df.empty:
        return "1"
    numeric_ids = pd.to_numeric(df["row_id"], errors="coerce").dropna()
    if numeric_ids.empty:
        return ""
    return str(int(numeric_ids.max()) + 1)


def append_evidence_row(row: dict[str, str], columns: list[str]) -> None:
    """Append one row to the evidence CSV while preserving existing rows."""
    with EVIDENCE_PATH.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writerow(row)


def run_validation() -> subprocess.CompletedProcess[str]:
    """Run the Python validator using the current interpreter."""
    return subprocess.run(
        [sys.executable, str(VALIDATOR_PATH)],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def page_dashboard_summary(evidence_df: pd.DataFrame, review_df: pd.DataFrame) -> None:
    st.title("Dashboard Summary")

    rows_needing_review = len(review_df) if not review_df.empty else 0
    col1, col2 = st.columns(2)
    col1.metric("Evidence rows", len(evidence_df))
    col2.metric("Rows needing review", rows_needing_review)

    chart_specs = [
        ("impact_domain", "Rows by Impact Domain"),
        ("evidence_strength", "Rows by Evidence Strength"),
        ("ioos_attribution_strength", "Rows by IOOS Attribution Strength"),
    ]

    for column, title in chart_specs:
        if column in evidence_df.columns:
            st.subheader(title)
            counts = evidence_df[column].replace("", "Blank").value_counts()
            st.bar_chart(counts)


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

    st.sidebar.title("IOOS Matrix")
    page = st.sidebar.radio(
        "Page",
        [
            "Dashboard Summary",
            "Evidence Matrix",
            "Review Needed",
            "Source Registry",
            "Add Evidence Row",
            "Run Validation",
        ],
    )

    if page == "Dashboard Summary":
        page_dashboard_summary(evidence_df, review_df)
    elif page == "Evidence Matrix":
        page_evidence_matrix(evidence_df)
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
