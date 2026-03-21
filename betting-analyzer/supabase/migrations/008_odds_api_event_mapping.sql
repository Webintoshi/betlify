alter table matches
add column if not exists odds_api_event_id bigint;

create unique index if not exists idx_matches_odds_api_event_id_unique
on matches(odds_api_event_id)
where odds_api_event_id is not null;

create index if not exists idx_matches_odds_api_event_id
on matches(odds_api_event_id);

create index if not exists idx_odds_history_match_bookmaker_market
on odds_history(match_id, bookmaker, market_type);
