-- Track the publication or last-updated year shown by each candidate source.

alter table if exists public.staged_evidence
  add column if not exists source_publication_year text not null default 'Unknown';

create index if not exists staged_evidence_source_publication_year_idx
  on public.staged_evidence(source_publication_year);

alter table if exists public."MARACOOS"
  add column if not exists source_publication_year text not null default 'Unknown';

create index if not exists maracoos_source_publication_year_idx
  on public."MARACOOS"(source_publication_year);

do $$
begin
  if to_regclass('public.staged_evidence') is not null
    and not exists (
      select 1 from pg_constraint
      where conname = 'staged_evidence_source_publication_year_check'
    )
  then
    alter table public.staged_evidence
      add constraint staged_evidence_source_publication_year_check
      check (source_publication_year = 'Unknown' or source_publication_year ~ '^(18|19|20)[0-9]{2}$');
  end if;

  if to_regclass('public."MARACOOS"') is not null
    and not exists (
      select 1 from pg_constraint
      where conname = 'maracoos_source_publication_year_check'
    )
  then
    alter table public."MARACOOS"
      add constraint maracoos_source_publication_year_check
      check (source_publication_year = 'Unknown' or source_publication_year ~ '^(18|19|20)[0-9]{2}$');
  end if;
end $$;

do $$
declare
  table_name text;
begin
  foreach table_name in array array[
    'staging_aoos_evidence',
    'staging_caricoos_evidence',
    'staging_cencoos_evidence',
    'staging_gcoos_evidence',
    'staging_glos_evidence',
    'staging_maracoos_evidence',
    'staging_nanoos_evidence',
    'staging_neracoos_evidence',
    'staging_pacioos_evidence',
    'staging_sccoos_evidence',
    'staging_secoora_evidence'
  ]
  loop
    if to_regclass('public.' || quote_ident(table_name)) is not null then
      execute format(
        'alter table public.%I add column if not exists source_publication_year text not null default %L',
        table_name,
        'Unknown'
      );
      execute format(
        'create index if not exists %I on public.%I(source_publication_year)',
        table_name || '_source_publication_year_idx',
        table_name
      );
      if not exists (
        select 1 from pg_constraint
        where conname = table_name || '_source_publication_year_check'
      ) then
        execute format(
          'alter table public.%I add constraint %I check (source_publication_year = ''Unknown'' or source_publication_year ~ ''^(18|19|20)[0-9]{2}$'')',
          table_name,
          table_name || '_source_publication_year_check'
        );
      end if;
    end if;
  end loop;
end $$;
