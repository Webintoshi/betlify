from __future__ import annotations

import logging
import os
from typing import Optional

from supabase import Client, create_client

logger = logging.getLogger(__name__)

LOCAL_FAKE_SERVICE_KEY = "local.local.local"


def _env_bool(name: str, default: bool = False) -> bool:
    raw = str(os.getenv(name, str(default))).strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return default


def _is_local_db_mode() -> bool:
    return _env_bool("LOCAL_DB_MODE", False)


def _resolve_supabase_env() -> tuple[str, str]:
    local_mode = _is_local_db_mode()
    supabase_url = str(os.getenv("SUPABASE_URL", "")).strip()
    supabase_service_key = str(os.getenv("SUPABASE_SERVICE_KEY", "")).strip()

    if local_mode:
        if not supabase_url:
            supabase_url = str(
                os.getenv("LOCAL_POSTGREST_URL", "http://postgrest:3000")
            ).strip()
        if not supabase_service_key:
            supabase_service_key = str(
                os.getenv("LOCAL_SUPABASE_SERVICE_KEY", LOCAL_FAKE_SERVICE_KEY)
            ).strip()

    return supabase_url, supabase_service_key


def build_supabase_client(*, required: bool = True) -> Optional[Client]:
    local_mode = _is_local_db_mode()
    supabase_url, supabase_service_key = _resolve_supabase_env()

    if (
        not supabase_url
        or not supabase_service_key
        or (not local_mode and "BURAYA_" in supabase_service_key)
    ):
        if required:
            raise RuntimeError(
                "Database connection config is missing. "
                "Set SUPABASE_URL and SUPABASE_SERVICE_KEY, or enable LOCAL_DB_MODE."
            )
        return None

    try:
        client = create_client(supabase_url, supabase_service_key)
        if local_mode:
            # Supabase client always appends /rest/v1 to supabase_url.
            # In local mode we point it directly to PostgREST root.
            rest_url = str(os.getenv("LOCAL_POSTGREST_URL", supabase_url)).strip().rstrip("/")
            client.rest_url = rest_url
            client._postgrest = None  # type: ignore[attr-defined]
        return client
    except Exception as exc:
        if required:
            raise RuntimeError("Database client initialization failed.") from exc
        logger.warning("Optional database client init failed: %s", exc)
        return None

