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
        '<h1 contenteditable="true">The Forecast Behind the Forecast: Ocean Observations Power America&rsquo;s Coastal Economy</h1>',
    )
    filled = filled.replace(
        '<span contenteditable="true">Prepared for: Office of ____</span>',
        '<span contenteditable="true">Prepared for: Congressional Staff</span>',
    )
    filled = filled.replace(
        '<span contenteditable="true">[Date]</span>',
        f'<span contenteditable="true">{escape(generated_date)}</span>',
    )

    lead = (
        f'<p class="lead" contenteditable="true">America&rsquo;s coastal economy depends on forecasts that start in the water. '
        f'IOOS and NOAA observing systems turn water-level, current, biological, chemical, and storm data into operational decisions for ports, shellfish managers, emergency responders, hatcheries, and coastal planners. '
        f'The live evidence matrix behind this brief currently contains {evidence_count} evidence rows and {source_count} registered sources; its strongest national business context is the Ocean Enterprise survey row, which reports: {escape(row14["metric"])}. '
        f'Case-study and modeled rows show measurable value in port navigation and coastal data infrastructure, while other rows document decision pathways that need updated valuation.</p>'
    )
    filled = replace_between(
        filled,
        '<p class="lead" contenteditable="true">',
        '\n\n  <div class="callout">',
        lead,
    )

    callout = f"""<div class="callout">
    <div class="label">WHY THIS MATTERS TO YOUR OFFICE</div>
    <ul>
      <li contenteditable="true"><b>Ports and maritime commerce:</b> {escape(row1["claim_allowed"])} The Tampa Bay case study metric is {escape(row1["metric"])}.</li>
      <li contenteditable="true"><b>Ocean data businesses:</b> {escape(row14["claim_allowed"])} The survey metric reports: {escape(row14["metric"])}.</li>
      <li contenteditable="true"><b>Public safety and hazards:</b> HF radar data support USCG search planning, glider observations support hurricane intensity forecasting, and NOAA water-level observations support coastal inundation decisions.</li>
      <li contenteditable="true"><b>Working waterfronts:</b> HAB forecasts and ocean acidification observations support shellfish closure, sampling, and hatchery timing decisions, but the matrix does not yet quantify IOOS-attributable savings for these rows.</li>
    </ul>
  </div>"""
    filled = replace_between(
        filled,
        '<div class="callout">',
        '\n\n  <h2 class="section">How IOOS Creates Economic Value</h2>',
        callout,
    )

    value_chain = f"""<h2 class="section">How IOOS Creates Economic Value</h2>
  <p contenteditable="true" style="margin:0 0 6px;">IOOS converts sustained ocean observations into trusted data products, forecasts, and decisions that keep coastal commerce and public safety systems moving.</p>
  <ul>
    <li contenteditable="true"><b>Observations:</b> PORTS&reg; water levels and currents, HF radar surface currents, gliders, ocean acidification stations, HAB observations, and long-term coastal water-level stations.</li>
    <li contenteditable="true"><b>Data Integration:</b> IOOS regional associations and NOAA systems standardize, quality-control, and distribute observations for operational users.</li>
    <li contenteditable="true"><b>Models &amp; Forecasts:</b> HAB forecasts, SAROPS drift prediction, hurricane intensity models, inundation dashboards, and port decision-support tools depend on these inputs.</li>
    <li contenteditable="true"><b>Decisions:</b> Pilots, port operators, shellfish managers, hatcheries, the Coast Guard, emergency managers, and planners act on the resulting information.</li>
    <li contenteditable="true"><b>Economic Outcomes:</b> The matrix documents avoided costs, loading efficiency, targeted closures, search efficiency, preparedness, business revenue, and time savings where sources support those claims.</li>
  </ul>"""
    filled = replace_between(
        filled,
        '<h2 class="section">How IOOS Creates Economic Value</h2>',
        '\n\n  <h2 class="section">Sector Snapshots</h2>',
        value_chain,
    )

    sectors = f"""<h2 class="section">Sector Snapshots</h2>
  <div class="vignette" contenteditable="true"><span class="sector">Commercial Fishing &amp; Shellfish: </span>HAB forecasts help managers focus testing and guide closure or advisory decisions; related project rows say forecasts can reduce unnecessary response costs and support targeted closures where operational use is documented. Ocean acidification rows show real-time observations used by shellfish growers and hatcheries, while the West Coast shellfish industry value in the matrix is risk context rather than a quantified IOOS savings claim.</div>
  <div class="vignette" contenteditable="true"><span class="sector">Maritime Shipping &amp; Navigation: </span>{escape(row1["claim_allowed"])} The matrix also includes a modeled national PORTS&reg; scenario: {escape(row3["metric"])}. That scenario is useful for investment framing but is labeled modeled and needs source verification.</div>
  <div class="vignette" contenteditable="true"><span class="sector">Coastal Hazards &amp; Emergency Response: </span>{escape(row9["claim_allowed"])} IOOS-coordinated glider observations support hurricane intensity forecasting, and NOAA water-level observations support coastal inundation monitoring and local flood decision-making. These are strong operational pathways, but the current rows do not assign avoided-loss dollars.</div>"""
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
