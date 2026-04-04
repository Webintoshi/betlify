# Betlify Split Deployment Guide

Bu dokuman frontend ve backend servislerini ayri calistirmak icin hazirlandi.

## 1. Backend Stack (DB + PostgREST + FastAPI)

1. Ornek env dosyasini olustur:
   - `cp .env.backend.example .env.backend`
2. Gerekli anahtarlari doldur (`API_FOOTBALL_KEY`, `THE_ODDS_API_KEY`, vb.).
3. Backend stack'i kaldir:
   - `docker compose --env-file .env.backend -f docker-compose.backend.yml up -d --build`
4. Saglik kontrol:
   - `http://localhost:8000/health`

## 2. Frontend Stack (Next.js)

1. Ornek env dosyasini olustur:
   - `cp .env.frontend.example .env.frontend`
2. `NEXT_PUBLIC_BACKEND_URL` alanina backend public URL yaz:
   - ornek: `https://api.example.com`
3. Frontend stack'i kaldir:
   - `docker compose --env-file .env.frontend -f docker-compose.frontend.yml up -d --build`
4. Frontend kontrol:
   - `http://localhost:3000`

## 3. Full Stack (Local tek komut)

Mevcut monolit compose dosyasiyla:
- `docker compose up -d --build`

## Veri Butunlugu ve Stabilite Notlari

- Kaynak dogrulugu: tum yazma/isleme akislarinda tek kaynak PostgreSQL (`predictions`, `results_tracker`, `coupons`).
- Ayrik deployment'ta backend kapaliyken frontend ham stack trace yerine kontrollu hata mesaji gosterir.
- `history` ekrani backend gecici erisilemezse "bos veri" modunda acilir ve UI kirilmaz.
- DB baslangic migration'lari yalnizca `db` container ilk olusumunda otomatik uygulanir.
- Uretim ortami icin periyodik DB yedegi (snapshot + WAL/point-in-time) tavsiye edilir.
