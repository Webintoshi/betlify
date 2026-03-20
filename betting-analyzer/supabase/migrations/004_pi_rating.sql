alter table teams
add column if not exists pi_rating numeric(8,2) default 1500;
