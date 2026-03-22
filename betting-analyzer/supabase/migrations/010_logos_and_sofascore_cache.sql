create extension if not exists "pgcrypto";

-- teams: logo cache metadata + enrichment sync timestamp
alter table teams
  add column if not exists logo_url text,
  add column if not exists logo_source text default 'sofascore',
  add column if not exists logo_status text default 'pending',
  add column if not exists logo_last_fetched_at timestamptz,
  add column if not exists logo_etag text,
  add column if not exists sofascore_last_synced_at timestamptz;

-- team season stats cache (SofaScore)
create table if not exists team_season_stats_cache (
  id uuid default gen_random_uuid() primary key,
  team_id uuid references teams(id) on delete cascade,
  team_sofascore_id integer not null,
  tournament_id integer not null,
  season_id integer not null,
  position integer default 0,
  matches_played integer default 0,
  goals_for numeric(8,3) default 0,
  goals_against numeric(8,3) default 0,
  goals_per_match numeric(8,3) default 0,
  goals_conceded_per_match numeric(8,3) default 0,
  clean_sheets integer default 0,
  assists integer default 0,
  expected_goals numeric(8,3) default 0,
  shots_on_target numeric(8,3) default 0,
  big_chances numeric(8,3) default 0,
  possession numeric(8,3) default 0,
  avg_rating numeric(8,3) default 0,
  updated_at timestamptz default now(),
  unique(team_id, tournament_id, season_id)
);

-- team top players cache (SofaScore)
create table if not exists team_top_players_cache (
  id uuid default gen_random_uuid() primary key,
  team_id uuid references teams(id) on delete cascade,
  team_sofascore_id integer not null,
  tournament_id integer,
  season_id integer,
  player_sofascore_id integer,
  player_name text not null,
  position text,
  rating numeric(5,2) default 0,
  minutes_played integer default 0,
  updated_at timestamptz default now(),
  unique(team_id, tournament_id, season_id, player_name)
);

-- standings cache (SofaScore)
create table if not exists league_standings_cache (
  id uuid default gen_random_uuid() primary key,
  tournament_id integer not null,
  season_id integer not null,
  team_id uuid references teams(id) on delete cascade,
  team_sofascore_id integer not null,
  team_name text,
  position integer default 0,
  played integer default 0,
  wins integer default 0,
  draws integer default 0,
  losses integer default 0,
  points integer default 0,
  goals_for integer default 0,
  goals_against integer default 0,
  goal_diff integer default 0,
  form text,
  updated_at timestamptz default now(),
  unique(tournament_id, season_id, team_sofascore_id)
);

create index if not exists idx_team_season_cache_team on team_season_stats_cache(team_id);
create index if not exists idx_team_season_cache_team_updated on team_season_stats_cache(team_id, updated_at desc);
create index if not exists idx_team_players_cache_team on team_top_players_cache(team_id);
create index if not exists idx_team_players_cache_team_updated on team_top_players_cache(team_id, updated_at desc);
create index if not exists idx_standings_cache_tournament on league_standings_cache(tournament_id, season_id);
create index if not exists idx_standings_cache_team on league_standings_cache(team_id);
