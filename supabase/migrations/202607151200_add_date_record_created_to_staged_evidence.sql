alter table if exists public.evidence_matrix
  add column if not exists date_record_created date not null default current_date;

alter table public.staged_evidence
  add column if not exists date_record_created date not null default current_date;

do $$
begin
  if to_regclass('public.evidence_matrix') is not null then
    execute 'create index if not exists evidence_matrix_date_record_created_idx on public.evidence_matrix(date_record_created)';
  end if;
end;
$$;

create index if not exists staged_evidence_date_record_created_idx
  on public.staged_evidence(date_record_created);
