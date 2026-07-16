# IOOS Economic Impact Evidence Matrix

This repository supports a structured evidence matrix for IOOS economic impact reporting. It keeps impact claims, source metadata, validation checks, and a local review dashboard in one GitHub-ready project.

## Repository Structure

```text
data/
  evidence_matrix.csv
  best_sources.csv
  source_registry.csv
  review_needed.csv
  staged_evidence.csv
scripts/
  validate_matrix.py
app/
  app.py
docs/
  methodology.md
  claim_strength_framework.md
  final_report_outline.md
outputs/
  summary_tables/
```

## What The Project Does

The project tracks evidence that can support IOOS economic impact claims, organized so each of the 11 IOOS Regional Associations has a durable section. The current project deliverable is the MARACOOS regional pilot, while the same app structure, regional prompts, and shared tables stay in place for future teams to continue building the dataset region by region.

Each evidence row captures the impact domain, IOOS component, user group, decision supported, economic pathway, metric, source, claim language, limitations, update frequency, regional code, and evidence ratings.

The live Supabase app now uses a pilot-first staging model. MARACOOS can stay in its existing `MARACOOS` table while the first regional build is being reviewed; shared candidate rows live in `staged_evidence`; curated source guidance lives in `best_sources`. Once MARACOOS rows are cleaned up, they can be backfilled into `staged_evidence` with `ioos_region_code = MARACOOS`.

The dashboard also includes an AI-assisted intake workflow. AI output uses a strict candidate-row schema, then the reviewer chooses the Supabase destination table in the upload form. The default remains `staged_evidence`, but the MARACOOS pilot can be sent to `MARACOOS` first so it is easier to track before later backfill.

See `docs/regional_intake_workflow.md` for the short version of the new regional intake direction.

## How The Evidence Matrix Works

- `data/staged_evidence.csv` mirrors the shared live evidence staging table.
- `data/best_sources.csv` stores the planned briefing-source shortlist from staged evidence.
- `MARACOOS` is the pilot-region intake table for MARACOOS candidate rows while the regional build is still being reviewed.
- Optional `staging_<region>_evidence` tables can hold future regional builds before they are merged into `staged_evidence`.
- `evidence_strength` describes how strong the underlying evidence is.
- `ioos_attribution_strength` describes how directly the impact can be attributed to an IOOS component.
- `source_verification_needed` controls whether rows are included under the current app display rule.
- `claim_allowed` should use language that matches the evidence and attribution strength.
- `limitations` should preserve caveats, source age, modeling assumptions, and verification needs.

Current app display rule: public evidence views show rows where `source_verification_needed` is `Yes`, matching the current staged/best-source review dataset. If the flag is later restored to its literal meaning ("Yes, this still needs verification"), change `APP_DISPLAY_SOURCE_VERIFICATION_NEEDED_VALUE` in `app/app.py` to `No` for public verified-only display.

See `docs/claim_strength_framework.md` for the rating framework.

## Install Requirements

Create and activate a virtual environment if desired, then install dependencies:

```powershell
python -m pip install -r requirements.txt
```

## Run Validation

From the repository root:

```powershell
python scripts/validate_matrix.py
```

The validator reads `data/evidence_matrix.csv` and `data/source_registry.csv`, writes `data/review_needed.csv`, and reports the number of errors and warnings.

## Run The Streamlit Dashboard Locally

From the repository root:

```powershell
streamlit run app/app.py
```

When `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` are available in `.env` or Streamlit secrets, the dashboard reads and writes the live Supabase tables. Local CSV files remain as import/export mirrors and as a fallback when Supabase credentials are not configured.

The dashboard includes:

- Dashboard summary charts
- Top-level Regions workspace with one section for each IOOS Regional Association and MARACOOS as the active pilot build
- Proposal-aligned Project Roadmap with timeline, objectives, governance rules, and table status
- Regional Builds workspace for one-region-at-a-time research, starting with MARACOOS
- Searchable and filterable evidence rows organized by impact domain
- Curated Best Sources workspace for briefing and final-report source selection
- Evidence Intake prompt templates for research-to-row, regional-build, and source-to-row workflows
- Strict candidate CSV validation and staged evidence review
- Review/Admin workspace for import, source checks, and regional builds

## Migrate Data To Supabase

This repository includes a migration path for Supabase project `spfyejzxqornsfmoansk`.

1. Open the Supabase SQL editor for the project and run:

```text
supabase/schema.sql
```

2. Create a local `.env` file from `.env.example` and paste the project service-role key:

```powershell
Copy-Item .env.example .env
```

The final `.env` should contain:

```text
SUPABASE_URL=https://spfyejzxqornsfmoansk.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
```

For Streamlit secrets, either use flat keys:

```toml
SUPABASE_URL = "https://spfyejzxqornsfmoansk.supabase.co"
SUPABASE_SERVICE_ROLE_KEY = "your-service-role-key"
```

or a nested Supabase section:

```toml
[supabase]
url = "https://spfyejzxqornsfmoansk.supabase.co"
service_role_key = "your-service-role-key"
```

Keep the service-role key private. It can bypass row-level security.

3. Preview the migration locally:

```powershell
python scripts/upload_to_supabase.py --dry-run
```

4. Upload the CSV data:

```powershell
python scripts/upload_to_supabase.py
```

The bulk upload script targets the shared live tables:

- `staged_evidence`
- `best_sources`

To upload only selected tables, pass `--tables`, for example:

```powershell
python scripts/upload_to_supabase.py --tables staged_evidence best_sources
```

To intentionally replace the MARACOOS pilot table from `outputs/MARACOOS_staged_evidence_ready_to_upload.csv`, pass it explicitly:

```powershell
python scripts/upload_to_supabase.py --tables MARACOOS
```

Use the Streamlit Evidence Intake uploader when you want to choose a candidate-row destination interactively. The upload form can send rows to:

- `staged_evidence` for shared staging
- `MARACOOS` for the current MARACOOS pilot table
- `staging_<region>_evidence` tables for future region-by-region intake
- a custom table that uses the same schema as `staged_evidence`

Do not use the bulk script for MARACOOS pilot uploads unless you intentionally want a full-table replacement workflow. The app uploader appends validated rows.

For source checks, open `Review / Admin` and switch the source review table from `Shared staged_evidence` to `MARACOOS table`.

## Evidence Intake Workflow

Use the Streamlit dashboard page named `Evidence Intake` for AI-assisted workflows:

- `Research Topic`: enter a research question or topic and copy the generated prompt.
- `Regional Build Prompt`: select a regional research target, starting with MARACOOS, and copy a stricter regional case-study prompt.
- `Add Source`: paste a source URL, title, report text, abstract, or excerpt and copy the generated extraction prompt.

The prompt builders require AI to return an actual `.csv` file using this exact candidate schema:

```text
row_id,Date record created,Impact domain,IOOS component,Region,IOOS region code,User group,Decision supported,Economic pathway,Metric,Metric year / dollar year,Source,Source URL,Evidence strength,IOOS attribution strength,Economic number type,IOOS role type,Source verification needed,Allowed use,Not allowed use,Limitations,Claim allowed,Update frequency,AI extraction notes,Prompt used
```

Upload the AI-generated CSV on the `Evidence Intake` page. The app rejects candidate rows unless all required columns are present and these fields are populated:

- `Source`
- `Source URL`
- `IOOS region code`
- `Claim allowed`
- `Limitations`
- `Evidence strength`
- `IOOS attribution strength`

`Evidence strength` and `IOOS attribution strength` must be exactly one of `Strong`, `Medium`, `Contextual`, `Modeled`, or `Needs verification`. Put any explanation for the rating in `Limitations` or `AI extraction notes`, not in the rating field. `IOOS region code` should use one or more semicolon-separated codes from `AOOS`, `CARICOOS`, `CeNCOOS`, `GCOOS`, `GLOS`, `MARACOOS`, `NANOOS`, `NERACOOS`, `PacIOOS`, `SCCOOS`, `SECOORA`, plus `National`, `Multiple`, or `Unknown` when needed. CSV fields that contain commas, quotes, or line breaks must be quoted.

`Economic number type` must be one of `Observed dollar benefit`, `Modeled dollar estimate`, `Dollar exposure/context`, `Operational metric only`, `No economic number`, or `Do not use`. `IOOS role type` must be one of `Direct impact source`, `Direct decision-support source`, `Backend data source`, `Partner/infrastructure source`, `Context only`, or `No IOOS attribution`. Use `Allowed use` and `Not allowed use` to state whether a row can support a hard-dollar claim, a modeled-dollar claim, an operational value claim, a backend attribution chain, or context only.

Blank `Date record created` values are defaulted to the upload date in `YYYY-MM-DD` format. Blank `Source verification needed` values are defaulted to `Yes`. `Prompt used` stores the prompt that generated the candidate row; when importing older CSVs, paste the prompt into the upload form to fill blank prompt provenance for every row. Candidate rows uploaded to `staged_evidence` appear on the `Staged Evidence` page, where reviewers can edit staged rows. Candidate rows uploaded to `MARACOOS` stay in the MARACOOS pilot table until they are reviewed and backfilled. Rows can only be accepted into the official matrix after `Source verification needed` is set to `No`; accepted rows are mapped into the existing `evidence_matrix.csv` and `source_registry.csv` structure.

Official evidence row IDs use the durable master-list format `EVID-####`.
Regional scope still belongs in `ioos_region_code`. A regional table is a temporary intake workspace, not the permanent source of truth.

## Regional Build Workflow

Use `data/regional_research_targets.csv` as the planning layer for one-region-at-a-time builds. The Streamlit `Regions` page turns those targets into 11 handoff-ready regional sections. The first active target, and the region intended to be completed in this project phase, is MARACOOS.

Do not add placeholder rows directly to `data/evidence_matrix.csv`. A regional build should generate source-backed candidate rows, upload them into the active regional intake table (`MARACOOS` for the current pilot, or another staging table later), verify source support and attribution, then backfill accepted candidate rows into `staged_evidence` or promote them into the master matrix.

The master matrix remains the certified national evidence set. Regional targets describe what to research; regional intake tables hold work-in-progress findings; `staged_evidence` is the shared review/backfill layer; accepted evidence rows become the durable master data. Future regional work should keep the same schema and include the appropriate `ioos_region_code` so rows can merge cleanly later.

## Add New Evidence Rows

Use the Streamlit dashboard page named `Add Evidence Row`. The form includes every column in `data/evidence_matrix.csv` and appends one new row without changing existing rows.

Required fields are:

- `impact_domain`
- `ioos_component`
- `source_id`
- `claim_allowed`
- `limitations`
- `evidence_strength`
- `ioos_attribution_strength`

After adding a row, run validation from the dashboard or with `python scripts/validate_matrix.py`.

## Quarterly IOOS Economic Impact Updates

For each quarterly update:

1. Add new or updated sources to `data/source_registry.csv`.
2. Add new evidence rows to `data/evidence_matrix.csv`.
3. Run validation and review `data/review_needed.csv`.
4. Resolve missing fields, invalid ratings, source mismatches, and unsupported claim language.
5. Refresh summary tables in `outputs/summary_tables/`.
6. Use the validated matrix and docs framework to update report-ready claims.
