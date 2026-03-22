alter table teams
  add column if not exists team_data_sync_status text default 'pending',
  add column if not exists team_data_last_fetched_at timestamptz,
  add column if not exists team_data_last_error text;

create table if not exists team_overview_cache (
  id uuid default gen_random_uuid() primary key,
  team_id uuid references teams(id) on delete cascade,
  team_sofascore_id integer not null,
  tournament_id integer not null,
  season_id integer not null,
  tournament_name text,
  season_name text,
  last_five_matches jsonb not null default '[]'::jsonb,
  form_last_ten jsonb not null default '{}'::jsonb,
  summary_stats jsonb not null default '{}'::jsonb,
  attack_stats jsonb not null default '{}'::jsonb,
  passing_stats jsonb not null default '{}'::jsonb,
  defending_stats jsonb not null default '{}'::jsonb,
  other_stats jsonb not null default '{}'::jsonb,
  raw_statistics_payload jsonb not null default '{}'::jsonb,
  updated_at timestamptz default now(),
  unique(team_id, tournament_id, season_id)
);

create table if not exists team_overview_daily_snapshots (
  id uuid default gen_random_uuid() primary key,
  snapshot_date date not null,
  team_id uuid references teams(id) on delete cascade,
  team_sofascore_id integer not null,
  tournament_id integer not null,
  season_id integer not null,
  payload jsonb not null default '{}'::jsonb,
  updated_at timestamptz default now(),
  unique(snapshot_date, team_id, tournament_id, season_id)
);

create index if not exists idx_team_overview_cache_team on team_overview_cache(team_id);
create index if not exists idx_team_overview_cache_team_sofascore on team_overview_cache(team_sofascore_id);
create index if not exists idx_team_overview_cache_tournament on team_overview_cache(tournament_id, season_id);
create index if not exists idx_team_overview_snapshot_team on team_overview_daily_snapshots(team_id);
create index if not exists idx_team_overview_snapshot_date on team_overview_daily_snapshots(snapshot_date);
