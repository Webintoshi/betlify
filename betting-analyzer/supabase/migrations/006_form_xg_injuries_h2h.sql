create extension if not exists "pgcrypto";

alter table if exists team_stats
add column if not exists xg_rolling_10 numeric(8, 3) not null default 0;

create table if not exists h2h (
  id uuid primary key default gen_random_uuid(),
  home_team_id uuid not null references teams(id) on delete cascade,
  away_team_id uuid not null references teams(id) on delete cascade,
  match_date timestamptz not null,
  home_goals smallint not null default 0,
  away_goals smallint not null default 0,
  league text,
  sofascore_id integer,
  is_cup boolean not null default false,
  created_at timestamptz not null default now()
);

alter table if exists h2h
add column if not exists is_cup boolean not null default false;

create unique index if not exists idx_h2h_sofascore_id_unique on h2h(sofascore_id) where sofascore_id is not null;
create index if not exists idx_h2h_home_away on h2h(home_team_id, away_team_id);
create index if not exists idx_h2h_match_date_desc on h2h(match_date desc);

create table if not exists match_injuries (
  id uuid primary key default gen_random_uuid(),
  match_id uuid not null references matches(id) on delete cascade,
  team_id uuid not null references teams(id) on delete cascade,
  player_name text not null,
  position text,
  status text not null,
  reason text,
  expected_return text,
  created_at timestamptz not null default now(),
  unique(match_id, team_id, player_name)
);

create index if not exists idx_match_injuries_match_id on match_injuries(match_id);
create index if not exists idx_match_injuries_team_id on match_injuries(team_id);
create index if not exists idx_match_injuries_status on match_injuries(status);