from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import httpx
from dotenv import load_dotenv
from supabase import Client, create_client

logger = logging.getLogger("weather")

BASE_URL = "https://api.openweathermap.org/data/2.5/weather"

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR.parent / ".env")
load_dotenv(BASE_DIR / ".env", override=True)


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        if value is None:
            return fallback
        return float(value)
    except (TypeError, ValueError):
        return fallback


class WeatherService:
    def __init__(self, *, supabase_client: Optional[Client] = None) -> None:
        self.api_key = os.getenv("OPENWEATHER_API_KEY", "")
        self.supabase = supabase_client or self._build_supabase_client()
        self.http_client = httpx.AsyncClient(timeout=12.0)

    @staticmethod
    def _build_supabase_client() -> Optional[Client]:
        supabase_url = os.getenv("SUPABASE_URL", "")
        supabase_service_key = os.getenv("SUPABASE_SERVICE_KEY", "")
        if not supabase_url or not supabase_service_key or "BURAYA_" in supabase_service_key:
            return None
        try:
            return create_client(supabase_url, supabase_service_key)
        except Exception:
            return None

    def _cache_key(self, city: str, match_datetime: str) -> str:
        return f"weather:{city.strip().lower()}:{match_datetime[:13]}"

    def _get_cached(self, cache_key: str) -> Optional[Dict[str, Any]]:
        if self.supabase is None:
            return None
        try:
            result = (
                self.supabase.table("api_cache")
                .select("payload,expires_at")
                .eq("cache_key", cache_key)
                .limit(1)
                .execute()
            )
            rows = result.data or []
            if not rows:
                return None
            row = rows[0]
            expires_at = row.get("expires_at")
            if not expires_at:
                return None
            expire_dt = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
            if expire_dt <= datetime.now(timezone.utc):
                return None
            payload = row.get("payload")
            return payload if isinstance(payload, dict) else None
        except Exception:
            return None

    def _set_cache(self, cache_key: str, payload: Dict[str, Any], ttl_seconds: int = 3 * 60 * 60) -> None:
        if self.supabase is None:
            return
        try:
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
            row = {
                "cache_key": cache_key,
                "payload": payload,
                "expires_at": expires_at.isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            self.supabase.table("api_cache").upsert(row, on_conflict="cache_key").execute()
        except Exception:
            return

    async def get_match_weather(self, city: str, match_datetime: str) -> Dict[str, Any]:
        default_payload = {
            "city": city,
            "match_datetime": match_datetime,
            "weather_score": 50.0,
            "temperature_c": None,
            "wind_kmh": None,
            "condition": None,
            "source": "default",
        }
        if not city.strip():
            return default_payload
        if not self.api_key:
            return default_payload

        cache_key = self._cache_key(city, match_datetime)
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        params = {
            "q": city,
            "appid": self.api_key,
            "units": "metric",
            "lang": "tr",
        }
        try:
            response = await self.http_client.get(BASE_URL, params=params, timeout=12.0)
            response.raise_for_status()
        except httpx.TimeoutException:
            logger.warning("OpenWeather timeout. city=%s", city)
            return default_payload
        except httpx.HTTPStatusError as exc:
            logger.warning("OpenWeather HTTP %s city=%s", exc.response.status_code, city)
            return default_payload
        except Exception as exc:
            logger.warning("OpenWeather unexpected error: %s", exc)
            return default_payload

        try:
            payload = response.json()
        except ValueError:
            return default_payload

        weather_rows = payload.get("weather", []) if isinstance(payload, dict) else []
        weather_main = ""
        if isinstance(weather_rows, list) and weather_rows and isinstance(weather_rows[0], dict):
            weather_main = str(weather_rows[0].get("main", "")).lower()

        temp_c = _safe_float(payload.get("main", {}).get("temp"), fallback=0.0) if isinstance(payload, dict) else 0.0
        wind_ms = _safe_float(payload.get("wind", {}).get("speed"), fallback=0.0) if isinstance(payload, dict) else 0.0
        wind_kmh = wind_ms * 3.6

        score = 50.0
        if "snow" in weather_main:
            score = min(score, 20.0)
        if "rain" in weather_main or "drizzle" in weather_main or "thunderstorm" in weather_main:
            score = min(score, 30.0)
        if wind_kmh > 50.0:
            score = min(score, 40.0)
        if temp_c > 35.0:
            score = min(score, 35.0)

        result = {
            "city": city,
            "match_datetime": match_datetime,
            "weather_score": score,
            "temperature_c": round(temp_c, 2),
            "wind_kmh": round(wind_kmh, 2),
            "condition": weather_main or None,
            "source": "openweathermap",
        }
        self._set_cache(cache_key, result)
        return result

    async def close(self) -> None:
        try:
            await self.http_client.aclose()
        except Exception:
            logger.exception("WeatherService close failed.")


_default_service = WeatherService()


def get_service() -> WeatherService:
    return _default_service


async def get_match_weather(city: str, match_datetime: str) -> Dict[str, Any]:
    return await _default_service.get_match_weather(city, match_datetime)
