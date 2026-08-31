-- Run this in your Supabase project's SQL editor (Database -> SQL Editor).
-- Safe to re-run: drops and recreates the table from scratch.
drop table if exists alert_rules cascade;

create table alert_rules (
  id bigint generated always as identity primary key,
  venue_id text not null,
  venue_name text not null,
  days text[] not null,       -- subset of 'mon','tue','wed','thu','fri','sat','sun'
  start_time text not null,   -- "HH:MM"
  end_time text not null,     -- "HH:MM"
  created_at timestamptz not null default now()
);

-- Row Level Security: this table only ever holds "which courts/times I want
-- alerted on" -- not sensitive -- so we allow the public anon key full access
-- rather than adding auth. Anyone with your Supabase URL + anon key (both
-- embedded in the public frontend JS) could edit these rules; that's a low-risk
-- annoyance, not a data-exposure issue. Keep the project private/unlisted if
-- you'd rather avoid even that.
alter table alert_rules enable row level security;

create policy "public read" on alert_rules
  for select using (true);

create policy "public write" on alert_rules
  for insert with check (true);

create policy "public delete" on alert_rules
  for delete using (true);
