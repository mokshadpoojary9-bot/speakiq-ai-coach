-- SpeakIQ AI Coach: optional storage of analysis results.
-- Run once in the Supabase SQL editor for your project. Safe to run again.
--
-- Only the backend reads and writes this table, using the service-role key, which bypasses
-- row-level security. Row-level security is enabled with NO policies, so the public anon key
-- (the one a browser could hold) can neither read nor write it.
-- Audio is never stored here: only the analysis result JSON, which includes transcript text.

create table if not exists public.analyses (
  id uuid primary key,
  access_key_hash text not null check (char_length(access_key_hash) = 64),
  result jsonb not null,
  created_at timestamptz not null default now()
);

alter table public.analyses enable row level security;

-- Belt and braces: remove any table privileges the anon and authenticated roles may have.
revoke all on table public.analyses from anon, authenticated;
