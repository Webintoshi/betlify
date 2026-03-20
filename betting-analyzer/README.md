# Bahis Analiz Sistemi

Kisisel kullanima yonelik, disa kapali, VPS/localhost ortaminda calisan bahis analiz ve kupon olusturma sistemi.

## Teknolojiler
- Frontend: Next.js 14 + TypeScript (strict) + Tailwind CSS
- Backend: FastAPI + APScheduler
- Veritabani: Supabase PostgreSQL
- Modelleme: XGBoost + ensemble yaklasimi icin temel altyapi
- Deployment: Docker Compose + Coolify webhook

## Klasor Yapisi
```text
betting-analyzer/
├── frontend/
├── backend/
├── supabase/
├── docker-compose.yml
└── .github/workflows/deploy.yml
```

## Hizli Baslangic
1. Koku dizinde `.env` dosyasini doldur (`.env.example` referans).
2. Lokal frontend icin `frontend/.env.local` kullan.
3. Lokal backend icin `backend/.env` kullan (opsiyonel, koku `.env` de okunur).
4. Supabase migration calistir:
   - `supabase/migrations/001_initial_schema.sql`
   - `supabase/migrations/002_stage2_environment_and_api.sql`
5. Uygulamayi ayaga kaldir:
   - `docker compose up --build`
6. Frontend:
   - [http://localhost:3000](http://localhost:3000)
7. Backend:
   - [http://localhost:8000/health](http://localhost:8000/health)

## Notlar
- Scheduler gorevleri:
  - 06:00: gunluk fikstur cekme
  - 2 saatte bir: canli oran guncelleme
  - 23:00: biten mac sonuclarini isleme
- `POST /analyze/{match_id}` endpointi analiz + EV hesaplama yapar ve `predictions` tablosuna yazar.
- Test endpointleri:
  - `GET /health`
  - `GET /test/fetch-today`
  - `GET /test/analyze/{match_id}`
  - `GET /test/odds/{fixture_id}`
