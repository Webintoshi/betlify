create extension if not exists "pgcrypto";

create table if not exists teams (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  league text not null,
  country text not null,
  market_value numeric(14, 2) default 0,
  created_at timestamptz not null default now()
);

create table if not exists matches (
  id uuid primary key default gen_random_uuid(),
  home_team_id uuid not null references teams(id) on delete restrict,
  away_team_id uuid not null references teams(id) on delete restrict,
  league text not null,
  match_date timestamptz not null,
  status text not null check (status in ('scheduled', 'live', 'finished')),
  season text not null,
  created_at timestamptz not null default now()
);

create table if not exists team_stats (
  id uuid primary key default gen_random_uuid(),
  team_id uuid not null references teams(id) on delete cascade,
  match_id uuid not null references matches(id) on delete cascade,
  goals_scored smallint not null default 0,
  goals_conceded smallint not null default 0,
  xg_for numeric(8, 3) not null default 0,
  xg_against numeric(8, 3) not null default 0,
  shots smallint not null default 0,
  shots_on_target smallint not null default 0,
  possession numeric(5, 2) not null default 0,
  form_last6 numeric(6, 3) not null default 0,
  updated_at timestamptz not null default now(),
  unique (team_id, match_id)
);

create table if not exists odds_history (
  id uuid primary key default gen_random_uuid(),
  match_id uuid not null references matches(id) on delete cascade,
  market_type text not null,
  bookmaker text not null,
  opening_odd numeric(8, 3),
  current_odd numeric(8, 3),
  closing_odd numeric(8, 3),
  recorded_at timestamptz not null default now()
);

create table if not exists predictions (
  id uuid primary key default gen_random_uuid(),
  match_id uuid not null references matches(id) on delete cascade,
  market_type text not null,
  predicted_outcome text not null,
  confidence_score numeric(5, 2) not null check (confidence_score >= 0 and confidence_score <= 100),
  ev_percentage numeric(8, 4) not null,
  recommended boolean not null default false,
  created_at timestamptz not null default now()
);

create table if not exists coupons (
  id uuid primary key default gen_random_uuid(),
  created_at timestamptz not null default now(),
  selections jsonb not null default '[]'::jsonb,
  total_odds numeric(8, 3) not null default 0,
  status text not null check (status in ('pending', 'won', 'lost', 'partial'))
);

create table if not exists results_tracker (
  id uuid primary key default gen_random_uuid(),
  prediction_id uuid not null unique references predictions(id) on delete cascade,
  actual_outcome text not null,
  was_correct boolean not null,
  resolved_at timestamptz not null default now()
);

create index if not exists idx_matches_match_date on matches(match_date);
create index if not exists idx_matches_status on matches(status);
create index if not exists idx_team_stats_team_id on team_stats(team_id);
create index if not exists idx_team_stats_match_id on team_stats(match_id);
create index if not exists idx_odds_history_match_id on odds_history(match_id);
create index if not exists idx_odds_history_market_type on odds_history(market_type);
create index if not exists idx_predictions_match_id on predictions(match_id);
create index if not exists idx_predictions_recommended on predictions(recommended);
create index if not exists idx_results_tracker_prediction_id on results_tracker(prediction_id);
