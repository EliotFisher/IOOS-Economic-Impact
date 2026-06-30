"""Fill the IOOS congressional briefing HTML template from Supabase data."""

from __future__ import annotations

import argparse
import csv
import html
import json
import os
from datetime import date
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TEMPLATE = Path.home() / "Downloads" / "IOOS_Congressional_Briefing_Template.html"
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


def escape(value: object) -> str:
    return html.escape(str(value or ""), quote=False).replace("\u00ae", "&reg;")


def row_by_id(evidence: list[dict[str, object]], row_id: str) -> dict[str, object]:
    for row in evidence:
        if str(row.get("row_id", "")) == row_id:
            return row
    raise RuntimeError(f"Expected evidence row {row_id} was not found.")


def source_label(row: dict[str, object], sources: dict[str, dict[str, object]]) -> str:
    source_id = str(row.get("source_id", ""))
    source = sources.get(source_id, {})
    label = escape(source.get("source_name") or source_id)
    verification = str(source.get("verification_status", "") or "").lower()
    needs_verification = str(row.get("source_verification_needed", "") or "").lower() == "yes"
    if needs_verification or "needs" in verification:
        label += " (needs verification)"
    return label


def replace_between(text: str, start_marker: str, end_marker: str, replacement: str) -> str:
    start = text.index(start_marker)
    end = text.index(end_marker, start)
    return text[:start] + replacement + text[end:]


def read_csv_count(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open(newline="", encoding="utf-8") as handle:
        return sum(1 for _ in csv.DictReader(handle))


def build_brief(template: str, evidence: list[dict[str, object]], sources: dict[str, dict[str, object]]) -> str:
    row1 = row_by_id(evidence, "1")
    row3 = row_by_id(evidence, "3")
    row5 = row_by_id(evidence, "5")
    row6 = row_by_id(evidence, "6")
    row9 = row_by_id(evidence, "9")
    row11 = row_by_id(evidence, "11")
    row13 = row_by_id(evidence, "13")
    row14 = row_by_id(evidence, "14")
    row15 = row_by_id(evidence, "15")
    row16 = row_by_id(evidence, "16")
    row17 = row_by_id(evidence, "17")

    source_count = len(sources)
    evidence_count = len(evidence)
    generated_date = date.today().strftime("%B %-d, %Y") if os.name != "nt" else date.today().strftime("%B %#d, %Y")

    filled = template.replace(
        '<h1 contenteditable="true">[Tagline &mdash; e.g., "The Forecast Behind the Forecast: Why Ocean Observations Power America&rsquo;s Coastal Economy"]</h1>',
        '<h1 contenteditable="true">Aide Memo: NOAA IOOS Economic Impact</h1>',
    )
    filled = filled.replace(
        '<title>IOOS Congressional Briefing Template</title>',
        '<title>IOOS Aide Memo</title>',
    )
    filled = filled.replace(
        '<div class="doc-label">Policy&nbsp;Briefing</div>',
        '<div class="doc-label">Aide&nbsp;Memo</div>',
    )
    filled = filled.replace(
        '<div class="toolbar">Click directly on any text to edit it. <b>This is a single page (page 2 continues below)</b> &mdash; print or save as PDF when ready (Cmd/Ctrl+P).</div>',
        '<div class="toolbar">Click directly on any text to edit it. <b>One-page aide memo.</b> &mdash; print or save as PDF when ready (Cmd/Ctrl+P).</div>',
    )
    filled = filled.replace(
        '<div class="kicker">IOOS Economic Impact</div>',
        '<div class="kicker">Legislative Memo</div>',
    )
    filled = filled.replace(
        '<span contenteditable="true">Prepared for: Office of ____</span>',
        '<span contenteditable="true">To: Congressional Staff | From: IOOS Economic Impact Team</span>',
    )
    filled = filled.replace(
        '<span contenteditable="true">[Date]</span>',
        f'<span contenteditable="true">{escape(generated_date)}</span>',
    )
    memo_header = f"""<div class="meta-line" style="display:block; line-height:1.45;">
    <div contenteditable="true"><b>To:</b> Congressional Staff</div>
    <div contenteditable="true"><b>From:</b> IOOS Economic Impact Team</div>
    <div contenteditable="true"><b>Date:</b> {escape(generated_date)}</div>
    <div contenteditable="true"><b>Re:</b> Sustain NOAA IOOS capacity and update economic valuations</div>
  </div>"""
    filled = filled.replace(
        f"""<div class="meta-line">
    <span contenteditable="true">To: Congressional Staff | From: IOOS Economic Impact Team</span>
    <span contenteditable="true">{escape(generated_date)}</span>
  </div>""",
        memo_header,
    )

    lead = (
        '<h2 class="section">Executive Summary</h2>\n'
        f'  <p class="lead" contenteditable="true"><b>Recommendation:</b> Sustain NOAA IOOS observing and data-integration capacity, and request updated economic valuations for the services most relevant to appropriations. '
        f'The current matrix shows clear economic relevance for ports, ocean-data businesses, shellfish/HAB management, and public safety, but several pathways need current IOOS-attributable estimates.</p>'
    )
    filled = replace_between(
        filled,
        '<p class="lead" contenteditable="true">',
        '\n\n  <div class="callout">',
        lead,
    )

    callout = f"""<h2 class="section">Background</h2>
  <p contenteditable="true" style="margin:0 0 10px;">IOOS turns ocean observations into operational information used by ports, pilots, emergency responders, shellfish managers, hatcheries, and coastal planners. This memo draws from the current evidence matrix: {evidence_count} evidence rows and {source_count} registered sources.</p>"""
    filled = replace_between(
        filled,
        '<div class="callout">',
        '\n\n  <h2 class="section">How IOOS Creates Economic Value</h2>',
        callout,
    )

    value_chain = f"""<h2 class="section">Analysis / Evidence</h2>
  <ul>
    <li contenteditable="true"><b>Maritime commerce:</b> Tampa Bay PORTS&reg; case-study benefits are {escape(row1["metric"])} ({escape(row1["metric_year_or_dollar_year"])}).</li>
    <li contenteditable="true"><b>Ocean-data economy:</b> The Ocean Enterprise survey reported {escape(row14["metric"])}. Use this as sector context, not direct IOOS attribution.</li>
    <li contenteditable="true"><b>Public safety:</b> HF radar supports Coast Guard search planning; gliders support hurricane intensity forecasting; NOAA water-level stations support flood decisions. Current rows document operational use, not avoided-loss dollars.</li>
    <li contenteditable="true"><b>Working waterfronts:</b> HAB forecasts and ocean acidification observations support targeted closures, monitoring, and hatchery timing. Quantified IOOS-attributable savings still need follow-up.</li>
  </ul>"""
    filled = replace_between(
        filled,
        '<h2 class="section">How IOOS Creates Economic Value</h2>',
        '\n\n  <h2 class="section">Sector Snapshots</h2>',
        value_chain,
    )

    sectors = f"""<h2 class="section">Recommendation</h2>
  <div class="ask-box">
    <div class="label">THE ASK</div>
    <div contenteditable="true">Sustain and strengthen NOAA IOOS observing, regional data integration, and decision-support services. Direct NOAA to update economic valuations for PORTS&reg;, HF radar/SAROPS, HAB forecasts, ocean acidification monitoring, hurricane gliders, and coastal inundation products before the next appropriations cycle.</div>
  </div>

  <div class="footnote" contenteditable="true">Source note: Auto-filled from live Supabase tables <b>evidence_matrix</b> and <b>source_registry</b> on {escape(generated_date)}. Strong figures are reported with caveats; modeled, contextual, and needs-verification values are not presented as direct IOOS-attributable benefits.</div>

  <div class="footer">
    <span contenteditable="true">IOOS Economic Impact Evidence Matrix | aide memo draft</span>
    <span contenteditable="true">Sources: {source_count} | Evidence rows: {evidence_count}</span>
  </div>"""
    filled = replace_between(
        filled,
        '<h2 class="section">Sector Snapshots</h2>',
        '\n\n</div>\n\n<div class="page" id="page2">',
        sectors,
    )

    numbers = f"""<h2 class="section" style="margin-top:0;">By the Numbers</h2>
  <table class="numbers">
    <tr><th>Metric</th><th>Value</th><th>Source</th></tr>
    <tr>
      <td contenteditable="true">Ocean observing and information business cluster</td>
      <td class="value" contenteditable="true">{escape(row14["metric"])}</td>
      <td class="source" contenteditable="true">{source_label(row14, sources)}</td>
    </tr>
    <tr>
      <td contenteditable="true">Tampa Bay PORTS&reg; case-study benefits</td>
      <td class="value" contenteditable="true">{escape(row1["metric"])} ({escape(row1["metric_year_or_dollar_year"])})</td>
      <td class="source" contenteditable="true">{source_label(row1, sources)}</td>
    </tr>
    <tr>
      <td contenteditable="true">Expanded national PORTS&reg; scenario</td>
      <td class="value" contenteditable="true">{escape(row3["metric"])}</td>
      <td class="source" contenteditable="true">{source_label(row3, sources)}</td>
    </tr>
    <tr>
      <td contenteditable="true">Related coastal data infrastructure benefits</td>
      <td class="value" contenteditable="true">{escape(row17["metric"])}</td>
      <td class="source" contenteditable="true">{source_label(row17, sources)}</td>
    </tr>
  </table>
  <div class="footnote" contenteditable="true">Auto-filled from live Supabase tables <b>evidence_matrix</b> and <b>source_registry</b> on {escape(generated_date)}. Wording follows each row&rsquo;s <b>claim_allowed</b> field; modeled, contextual, and needs-verification values are not presented as direct IOOS-attributable benefits.</div>"""
    filled = replace_between(
        filled,
        '<h2 class="section" style="margin-top:0;">By the Numbers</h2>',
        '\n\n  <h2 class="section">Risk of Underinvestment</h2>',
        numbers,
    )

    risk = f"""<h2 class="section">Risk of Underinvestment</h2>
  <p contenteditable="true" style="margin:0 0 6px;">Underinvestment erodes the observing, integration, and forecast chain before users see it: fewer trusted inputs, less reliable decision support, and weaker evidence for economic returns.</p>
  <ul>
    <li contenteditable="true">Ports and pilots lose real-time water-level, current, meteorological, and air-gap information that supports safe navigation and loading decisions.</li>
    <li contenteditable="true">Shellfish managers and hatcheries lose forecast and early-warning data used for targeted monitoring, closures, intake timing, and production scheduling.</li>
    <li contenteditable="true">USCG planners, hurricane forecasters, emergency managers, and coastal planners lose surface-current, glider, and water-level observations that support search planning, intensity forecasts, and flood response.</li>
  </ul>"""
    filled = replace_between(
        filled,
        '<h2 class="section">Risk of Underinvestment</h2>',
        '\n\n  <div class="ask-box">',
        risk,
    )

    ask = """<div class="ask-box">
    <div class="label">THE ASK</div>
    <div contenteditable="true">Sustain and strengthen NOAA IOOS observing, regional data integration, and decision-support services, and direct NOAA to update economic valuation for PORTS&reg;, HF radar, HAB forecasts, ocean acidification monitoring, hurricane gliders, and coastal hazards products so appropriators have current benefit estimates.</div>
  </div>"""
    filled = replace_between(
        filled,
        '<div class="ask-box">',
        '\n\n  <div class="footer">',
        ask,
    )

    footer = f"""<div class="footer">
    <span contenteditable="true">IOOS Economic Impact Evidence Matrix | Supabase-backed draft</span>
    <span contenteditable="true">Live source rows: {source_count} | Evidence rows: {evidence_count}</span>
  </div>"""
    filled = replace_between(
        filled,
        '<div class="footer">',
        '\n\n</div>\n\n</body>',
        footer,
    )

    page2_start = '\n\n<div class="page" id="page2">'
    page2_end = '\n\n</body>'
    if page2_start in filled:
        filled = replace_between(filled, page2_start, page2_end, "\n")

    return filled


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    template = args.template.read_text(encoding="utf-8")
    evidence, sources = load_live_data()
    filled = build_brief(template, evidence, sources)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(filled, encoding="utf-8")

    local_rows = read_csv_count(REPO_ROOT / "data" / "evidence_matrix.csv")
    print(f"Wrote {args.output}")
    print(f"Supabase evidence rows: {len(evidence)}; source rows: {len(sources)}; local mirror rows: {local_rows}")


if __name__ == "__main__":
    main()
