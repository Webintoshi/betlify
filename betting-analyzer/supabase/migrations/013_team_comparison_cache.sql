alter table teams
  add column if not exists team_comparison_last_used_at timestamptz;

create table if not exists team_comparison_cache (
  id uuid default gen_random_uuid() primary key,
  request_hash text not null unique,
  home_team_id uuid references teams(id) on delete cascade,
  away_team_id uuid references teams(id) on delete cascade,
  scope text not null default 'primary_current',
  season_mode text not null default 'current',
  data_window integer not null default 10,
  date_from date,
  date_to date,
  selected_tournament_id integer,
  selected_season_id integer,
  comparison_payload jsonb not null default '{}'::jsonb,
  feature_snapshot jsonb not null default '{}'::jsonb,
  robots_payload jsonb not null default '{}'::jsonb,
  confidence_score numeric(6,2) not null default 0,
  data_quality_score numeric(6,2) not null default 0,
  model_version text not null,
  expires_at timestamptz not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists team_comparison_logs (
  id uuid default gen_random_uuid() primary key,
  request_hash text not null,
  home_team_id uuid references teams(id) on delete cascade,
  away_team_id uuid references teams(id) on delete cascade,
  request_payload jsonb not null default '{}'::jsonb,
  included_match_ids jsonb not null default '[]'::jsonb,
  feature_snapshot jsonb not null default '{}'::jsonb,
  scenario_snapshot jsonb not null default '{}'::jsonb,
  robots_payload jsonb not null default '{}'::jsonb,
  confidence_score numeric(6,2) not null default 0,
  data_quality_score numeric(6,2) not null default 0,
  cache_hit boolean not null default false,
  model_version text not null,
  created_at timestamptz not null default now()
);

create index if not exists idx_team_comparison_cache_home_team on team_comparison_cache(home_team_id);
create index if not exists idx_team_comparison_cache_away_team on team_comparison_cache(away_team_id);
create index if not exists idx_team_comparison_cache_expires_at on team_comparison_cache(expires_at);
create index if not exists idx_team_comparison_logs_request_hash on team_comparison_logs(request_hash);
create index if not exists idx_team_comparison_logs_home_team on team_comparison_logs(home_team_id);
create index if not exists idx_team_comparison_logs_away_team on team_comparison_logs(away_team_id);
create index if not exists idx_team_comparison_logs_created_at on team_comparison_logs(created_at);
