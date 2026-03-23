from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from typing import Any, Dict, Optional

SUPPORTED_SCOPES = ("primary_current", "all_competitions", "common_tournament")
SUPPORTED_WINDOWS = (5, 10, 20)
SUPPORTED_ROBOTS = ("ana", "bma", "gma")
DEFAULT_SCOPE = "primary_current"
DEFAULT_SEASON_MODE = "current"
DEFAULT_DATA_WINDOW = 10
DEFAULT_ROBOT = "ana"
COMPARISON_MODEL_VERSION = "team-comparison-v2"


@dataclass(frozen=True)
class TeamComparisonRequest:
    home_team_id: str
    away_team_id: str
    scope: str = DEFAULT_SCOPE
    data_window: int = DEFAULT_DATA_WINDOW
    season_mode: str = DEFAULT_SEASON_MODE
    tournament_id: Optional[int] = None
    season_id: Optional[int] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    refresh: bool = False

    def validate(self) -> None:
        if not self.home_team_id or not self.away_team_id:
            raise ValueError("Her iki takim da secilmelidir.")
        if self.home_team_id == self.away_team_id:
            raise ValueError("Ayni takim iki kez secilemez.")
        if self.scope not in SUPPORTED_SCOPES:
            raise ValueError("Desteklenmeyen comparison scope.")
        if int(self.data_window) not in SUPPORTED_WINDOWS:
            raise ValueError("Desteklenmeyen data window.")
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("Baslangic tarihi bitis tarihinden buyuk olamaz.")

    def to_payload(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["data_window"] = int(self.data_window)
        payload["refresh"] = bool(self.refresh)
        return payload


@dataclass(frozen=True)
class TeamComparisonMeta:
    default_scope: str = DEFAULT_SCOPE
    default_data_window: int = DEFAULT_DATA_WINDOW
    default_robot: str = DEFAULT_ROBOT
    model_version: str = COMPARISON_MODEL_VERSION

    def to_payload(self) -> Dict[str, Any]:
        return {
            "default_scope": self.default_scope,
            "default_data_window": self.default_data_window,
            "default_robot": self.default_robot,
            "model_version": self.model_version,
            "supported_scopes": list(SUPPORTED_SCOPES),
            "supported_windows": list(SUPPORTED_WINDOWS),
            "supported_robots": list(SUPPORTED_ROBOTS),
        }


def coerce_optional_date(value: Optional[str]) -> Optional[str]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        raise ValueError(f"Gecersiz tarih: {text}") from None
