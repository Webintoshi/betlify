# Coolify Deployment (Project: x)

Bu rehber backend + frontend uygulamasini tek Coolify projesinde ayaga kaldirmak icindir.

## 1) Git repository
- Repository: `https://github.com/Webintoshi/betify.git`
- Branch: `main`
- Compose file: `docker-compose.coolify.yml`

## 2) Coolify proje yapisi
Coolify uzerinde `x` adinda bir proje olusturup tek compose stack olarak deploy et:
- Service type: Docker Compose
- Compose path: `docker-compose.coolify.yml`
- Environment file: `.env.coolify` (icerik `.env.coolify.example` uzerinden)

## 3) Gerekli ortam degiskenleri
Minimum zorunlu alanlar:
- `SUPABASE_URL` (`https://<your-supabase-host>/rest/v1`)
- `SUPABASE_SERVICE_KEY`
- `NEXT_PUBLIC_SUPABASE_URL`
- `NEXT_PUBLIC_SUPABASE_ANON_KEY`
- `CORS_ALLOW_ORIGINS`

Tavsiye edilen:
- `NEXT_PUBLIC_BACKEND_URL=/api/backend`
- `BACKEND_INTERNAL_URL=http://backend:8000`
- `SERVICE_URL_BACKEND=http://backend:8000`
- `BACKEND_URL=http://backend:8000`

## 4) Health checks
- Backend health: `/health`
- Frontend uygulama: `/`

## 5) Doðrulama
Deploy sonrasi asagidaki URL'leri test et:
- Frontend ana sayfa: `https://<frontend-domain>/`
- Backend health: `https://<backend-domain>/health`
- Frontend backend proxy: `https://<frontend-domain>/api/backend/health`

## 6) Notlar
- Self-hosted Supabase dis servistir; bu compose dosyasi DB container baslatmaz.
- Frontend ve backend ayridir; frontend backend'e server-side proxy ve env URL'leriyle baglanir.
- Bu degisiklikler sadece bu repo ve stack icin tasarlanmistir.
