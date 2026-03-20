create table if not exists odds (
  id uuid primary key default gen_random_uuid(),
  match_id uuid not null references matches(id) on delete cascade,
  market text not null,
  odd numeric(10, 4) not null,
  ev numeric(12, 6),
  recorded_at timestamptz not null default now(),
  unique (match_id, market)
);

alter table matches
add column if not exists best_bet text;

create index if not exists idx_odds_match_id on odds(match_id);
create index if not exists idx_odds_market on odds(market);
create index if not exists idx_odds_recorded_at on odds(recorded_at desc);

