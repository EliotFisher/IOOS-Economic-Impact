-- Normalize the master-list model.
--
-- One official evidence table should hold all accepted rows, with
-- ioos_region_code carrying regional scope. best_sources is retained as the
-- curated briefing shortlist and also gets ioos_region_code for filtering.

alter table public.evidence_matrix
  add column if not exists ioos_region_code text not null default 'Unknown';

alter table public.staged_evidence
  add column if not exists ioos_region_code text not null default 'Unknown';

alter table public.best_sources
  add column if not exists ioos_region_code text not null default 'Unknown';

create index if not exists evidence_matrix_ioos_region_code_idx
  on public.evidence_matrix(ioos_region_code);

create index if not exists best_sources_ioos_region_code_idx
  on public.best_sources(ioos_region_code);
