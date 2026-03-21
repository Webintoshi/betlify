-- Betfair-only gecis temizligi
-- Sofascore kaynakli legacy kayitlari temizler ve referans kolonlarini sifirlar.

-- 1) Sofascore market tipindeki tahminleri ve bunlara bagli result tracker kayitlarini sil
with legacy_predictions as (
  select id
  from predictions
  where market_type ilike 'SOFASCORE_%'
)
delete from results_tracker
where prediction_id in (select id from legacy_predictions);

delete from predictions
where market_type ilike 'SOFASCORE_%';

-- 2) Sofascore bookmaker kayitli odds history satirlarini sil
delete from odds_history
where bookmaker ilike 'sofascore%';

-- 3) Sofascore referans id kolonlarini temizle
update matches
set sofascore_id = null
where sofascore_id is not null;

update teams
set sofascore_id = null
where sofascore_id is not null;

-- 4) Sofascore kaynakli H2H satirlarini temizle
delete from h2h
where sofascore_id is not null;

