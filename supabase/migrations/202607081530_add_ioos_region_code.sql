-- Add normalized IOOS regional association codes to evidence tables.
-- Run this in the Supabase SQL editor before uploading CSV data that includes
-- ioos_region_code / IOOS region code.

alter table public.evidence_matrix
  add column if not exists ioos_region_code text not null default 'Unknown';

alter table public.staged_evidence
  add column if not exists ioos_region_code text not null default 'Unknown';

create index if not exists evidence_matrix_ioos_region_code_idx
  on public.evidence_matrix(ioos_region_code);
