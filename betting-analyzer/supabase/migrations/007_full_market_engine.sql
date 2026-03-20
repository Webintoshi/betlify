alter table predictions
add column if not exists kelly_pct numeric(5,2) default 0,
add column if not exists lambda_home numeric(6,4),
add column if not exists lambda_away numeric(6,4),
add column if not exists ht_lambda_home numeric(6,4),
add column if not exists ht_lambda_away numeric(6,4);

create table if not exists market_probabilities (
  id uuid default gen_random_uuid() primary key,
  match_id uuid not null references matches(id) on delete cascade,
  market text not null,
  probability numeric(8,6) not null,
  lambda_home numeric(6,4),
  lambda_away numeric(6,4),
  model_version text default 'dixon-coles-v1',
  created_at timestamptz default now(),
  unique (match_id, market)
);

create table if not exists ht_stats (
  id uuid default gen_random_uuid() primary key,
  team_id uuid not null references teams(id) on delete cascade,
  season text,
  ht_goals_scored_avg numeric(4,2),
  ht_goals_conceded_avg numeric(4,2),
  ht_goals_ratio numeric(4,2),
  updated_at timestamptz default now(),
  unique(team_id, season)
);

create index if not exists idx_market_probabilities_match_id on market_probabilities(match_id);
create index if not exists idx_market_probabilities_market on market_probabilities(market);
create index if not exists idx_ht_stats_team_id on ht_stats(team_id);