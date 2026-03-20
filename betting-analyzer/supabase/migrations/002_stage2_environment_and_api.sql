alter table matches
add column if not exists ht_home smallint,
add column if not exists ht_away smallint,
add column if not exists ft_home smallint,
add column if not exists ft_away smallint,
add column if not exists api_match_id integer unique;

alter table teams
add column if not exists api_team_id integer unique;

create table if not exists api_cache (
  cache_key text primary key,
  payload jsonb not null,
  expires_at timestamptz not null,
  updated_at timestamptz not null default now()
);

create index if not exists idx_api_cache_expires_at on api_cache (expires_at);
