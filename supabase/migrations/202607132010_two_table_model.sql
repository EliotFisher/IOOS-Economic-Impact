-- Consolidate Supabase to the current shared-table model:
--   public.staged_evidence: shared evidence/candidate rows after backfill
--   public.best_sources: curated source shortlist
--   public."MARACOOS": pilot-region intake rows kept separate during review
--
-- Run only after confirming any old evidence_matrix/source_registry data has
-- been migrated into staged_evidence or is no longer needed.

drop table if exists public.review_needed;
drop table if exists public.evidence_matrix;
drop table if exists public.source_registry;

alter table public.staged_evidence
  add column if not exists ioos_region_code text not null default 'Unknown',
  add column if not exists economic_number_type text not null default 'No economic number',
  add column if not exists ioos_role_type text not null default 'Partner/infrastructure source',
  add column if not exists allowed_use text not null default 'Needs manual claim-use classification before briefing use.',
  add column if not exists not_allowed_use text not null default 'Do not present as IOOS-attributable economic return until reviewed.';

alter table public.best_sources
  add column if not exists ioos_region_code text not null default 'Unknown';

create index if not exists staged_evidence_impact_domain_idx
  on public.staged_evidence(impact_domain);

create index if not exists staged_evidence_ioos_region_code_idx
  on public.staged_evidence(ioos_region_code);

create index if not exists staged_evidence_source_verification_needed_idx
  on public.staged_evidence(source_verification_needed);

create index if not exists staged_evidence_economic_number_type_idx
  on public.staged_evidence(economic_number_type);

create index if not exists staged_evidence_ioos_role_type_idx
  on public.staged_evidence(ioos_role_type);

create index if not exists best_sources_ioos_region_code_idx
  on public.best_sources(ioos_region_code);

create index if not exists best_sources_source_verification_needed_idx
  on public.best_sources(source_verification_needed);
