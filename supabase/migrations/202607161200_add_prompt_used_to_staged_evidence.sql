-- Track the prompt that produced each AI-generated candidate row.

alter table public.staged_evidence
  add column if not exists prompt_used text not null default '';
