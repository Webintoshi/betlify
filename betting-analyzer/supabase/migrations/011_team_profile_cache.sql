create extension if not exists "pgcrypto";

alter table teams
  add column if not exists slug text,
  add column if not exists sofascore_team_url text,
  add column if not exists coach_name text,
  add column if not exists coach_sofascore_id integer,
  add column if not exists team_status text default 'active',
  add column if not exists profile_last_fetched_at timestamptz,
  add column if not exists profile_source text default 'sofascore',
  add column if not exists profile_sync_status text default 'pending';

create table if not exists team_profile_cache (
  id uuid default gen_random_uuid() primary key,
  team_id uuid references teams(id) on delete cascade,
  team_sofascore_id integer not null unique,
  team_name text not null,
  country text,
  logo_url text,
  coach_name text,
  coach_sofascore_id integer,
  sofascore_url text,
  payload jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);

create index if not exists idx_teams_profile_sync_status on teams(profile_sync_status);
create index if not exists idx_teams_sofascore_team_url on teams(sofascore_team_url);
create index if not exists idx_team_profile_cache_team_id on team_profile_cache(team_id);
create index if not exists idx_team_profile_cache_updated_at on team_profile_cache(updated_at desc);
