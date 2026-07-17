# Regional Intake Workflow

## Direction

The app should support one-region-at-a-time evidence building. MARACOOS is the active pilot, so MARACOOS candidate rows can live in the existing `MARACOOS` Supabase table while they are still being reviewed.

The shared `staged_evidence` table remains the common review/backfill layer. Once MARACOOS rows are cleaned up, accepted rows can be copied or promoted into `staged_evidence` with `ioos_region_code = MARACOOS`.

## Table Roles

- `MARACOOS`: active pilot intake table for MARACOOS candidate CSV uploads.
- `staged_evidence`: shared candidate/evidence table used after review or backfill.
- `best_sources`: curated source shortlist and briefing guidance.
- `staging_<region>_evidence`: optional future regional intake tables using the same schema as `staged_evidence`.

Regional tables are temporary workspaces. The permanent regional identity still belongs in the `ioos_region_code` column so rows can merge cleanly later.

## Upload Path

Use the Streamlit `Evidence Intake` upload form for normal CSV intake. After the CSV passes validation, choose the Supabase destination table:

- MARACOOS CSVs default to `Existing MARACOOS table`.
- Non-MARACOOS CSVs default to `Shared staged_evidence`.
- A custom table can be used if it has the same schema as `staged_evidence`.

The app uploader appends rows. The bulk script is for intentional table replacement only.

Use `Review / Admin` -> `MARACOOS table` to verify sources directly from the `MARACOOS` table before backfill.

Regional prompts include editable source publication/update-year filters plus a short duplicate guard using existing rows from the selected evidence set. If the AI cannot find enough non-duplicate evidence inside the selected year window, it should return fewer rows instead of padding the CSV.

## Backfill Path

1. Upload MARACOOS candidate rows into `MARACOOS`.
2. Review source support, claim language, limitations, and attribution.
3. Keep `ioos_region_code = MARACOOS` on accepted rows.
4. Backfill reviewed rows into `staged_evidence` when the pilot set is ready.
5. Promote final accepted rows into the durable matrix/report workflow.
