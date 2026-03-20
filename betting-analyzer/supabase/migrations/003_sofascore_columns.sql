alter table matches
add column if not exists sofascore_id integer unique;

alter table teams
add column if not exists sofascore_id integer unique;
