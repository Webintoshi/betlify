from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from api_football import ApiFootballService, get_service as get_api_service
from config import DEFAULT_SEASON, TRACKED_LEAGUE_IDS
from odds_tracker import OddsTrackerService
from pi_rating import update_team_pi_ratings
from services.odds_scraper import OddsScraperService, get_service as get_odds_scraper_service
from sofascore import SofaScoreService, get_service as get_sofascore_service
from transfermarkt import TransfermarktService, get_service as get_transfermarkt_service

logger = logging.getLogger(__name__)


def _safe_int(value: Any, fallback: int = 0) -> int:
    try:
        if value is None:
            return fallback
        return int(value)
    except (TypeError, ValueError):
        return fallback


class BettingScheduler:
    def __init__(self) -> None:
        self.timezone = ZoneInfo("Europe/Istanbul")
        self.scheduler = AsyncIOScheduler(timezone=self.timezone)
        self.api_service: ApiFootballService = get_api_service()
        self.supabase = self.api_service.supabase
        self.odds_tracker = OddsTrackerService(supabase_client=self.supabase)
        self.odds_scraper: OddsScraperService = get_odds_scraper_service()
        self.sofascore: SofaScoreService = get_sofascore_service()
        self.transfermarkt: TransfermarktService = get_transfermarkt_service()

    def _today_and_tomorrow(self) -> List[str]:
        today = datetime.now(self.timezone).date()
        tomorrow = today + timedelta(days=1)
        return [today.isoformat(), tomorrow.isoformat()]

    def scheduler_status(self) -> Dict[str, Any]:
        jobs = []
        for job in self.scheduler.get_jobs():
            jobs.append(
                {
                    "id": job.id,
                    "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
                }
            )
        return {"running": self.scheduler.running, "jobs": jobs}

    async def fetch_specific_dates(self, dates: List[str]) -> Dict[str, Any]:
        total_saved = 0
        by_date: Dict[str, int] = {}
        for date_str in dates:
            rows = await self.api_service.get_fixtures_by_date(date_str)
            by_date[date_str] = len(rows)
            total_saved += len(rows)
        return {"total_saved": total_saved, "by_date": by_date}

    async def fetch_today_and_tomorrow_fixtures(self) -> Dict[str, Any]:
        result = await self.fetch_specific_dates(self._today_and_tomorrow())
        logger.info(
            "Gunluk fikstur gorevi tamamlandi. total=%s detay=%s",
            result["total_saved"],
            result["by_date"],
        )
        return result

    async def refresh_upcoming_odds(self) -> Dict[str, Any]:
        if self.supabase is None:
            return {"processed_matches": 0, "odds_rows": 0}

        today = datetime.now(self.timezone).date().isoformat()
        if self.odds_tracker.requests_remaining is not None and self.odds_tracker.requests_remaining < 20 and self.odds_tracker.low_quota_day == today:
            logger.warning("Kalan API istegi az (%s), oran guncellemesi atlandi", self.odds_tracker.requests_remaining)
            return {"processed_matches": 0, "odds_rows": 0, "skipped": True}

        try:
            upcoming_result = (
                self.supabase.table("matches")
                .select("id,api_match_id,league,status,match_date")
                .in_("status", ["scheduled", "live"])
                .order("match_date")
                .execute()
            )
            upcoming = upcoming_result.data or []
        except Exception:
            logger.exception("Yaklasan maclar okunamadi.")
            return {"processed_matches": 0, "odds_rows": 0}

        # The Odds API side feed (league-level).
        for league_id in TRACKED_LEAGUE_IDS:
            await self.odds_tracker.get_current_odds(league_id)

        processed = 0
        odds_rows = 0
        for match in upcoming:
            api_match_id = _safe_int(match.get("api_match_id"))
            match_id = str(match.get("id"))
            if api_match_id <= 0:
                continue
            rows = await self.api_service.get_odds(api_match_id)
            odds_rows += len(rows or [])
            await self.odds_tracker.calculate_line_movement(match_id)
            processed += 1

        logger.info("Oran guncellemesi tamamlandi. match=%s odds_rows=%s", processed, odds_rows)
        return {"processed_matches": processed, "odds_rows": odds_rows}

    @staticmethod
    def _is_prediction_correct(predicted: str, score_data: Dict[str, int]) -> bool:
        ft_home = _safe_int(score_data.get("ft_home"))
        ft_away = _safe_int(score_data.get("ft_away"))
        ht_home = _safe_int(score_data.get("ht_home"))
        ht_away = _safe_int(score_data.get("ht_away"))
        predicted = (predicted or "").upper()

        if predicted in {"MS1", "SHARP_HOME"}:
            return ft_home > ft_away
        if predicted == "MSX":
            return ft_home == ft_away
        if predicted == "MS2":
            return ft_away > ft_home
        if predicted == "IY1":
            return ht_home > ht_away
        if predicted == "IYX":
            return ht_home == ht_away
        if predicted == "IY2":
            return ht_away > ht_home
        if predicted == "KG_VAR":
            return ft_home > 0 and ft_away > 0
        if predicted == "KG_YOK":
            return not (ft_home > 0 and ft_away > 0)
        return False

    def _update_results_for_match(self, match_id: str, score_data: Dict[str, int]) -> Dict[str, int]:
        if self.supabase is None:
            return {"resolved": 0, "correct": 0}

        resolved = 0
        correct = 0
        try:
            result = (
                self.supabase.table("predictions")
                .select("id,predicted_outcome")
                .eq("match_id", match_id)
                .execute()
            )
            predictions = result.data or []
        except Exception:
            logger.exception("Prediction listesi okunamadi. match_id=%s", match_id)
            return {"resolved": 0, "correct": 0}

        for prediction in predictions:
            prediction_id = prediction.get("id")
            if not prediction_id:
                continue
            predicted_outcome = str(prediction.get("predicted_outcome", ""))
            was_correct = self._is_prediction_correct(predicted_outcome, score_data)
            row = {
                "prediction_id": prediction_id,
                "actual_outcome": f"{score_data.get('ft_home', 0)}-{score_data.get('ft_away', 0)}",
                "was_correct": was_correct,
                "resolved_at": datetime.now(self.timezone).isoformat(),
            }
            try:
                self.supabase.table("results_tracker").upsert(row, on_conflict="prediction_id").execute()
                resolved += 1
                if was_correct:
                    correct += 1
            except Exception:
                logger.exception("results_tracker update basarisiz. prediction_id=%s", prediction_id)

        return {"resolved": resolved, "correct": correct}

    async def reconcile_finished_matches(self) -> Dict[str, Any]:
        if self.supabase is None:
            return {"finished_matches": 0, "resolved_predictions": 0, "accuracy_pct": 0.0}

        today = datetime.now(self.timezone).date().isoformat()
        await self.api_service.get_fixtures_by_date(today)

        try:
            result = (
                self.supabase.table("matches")
                .select("id,ht_home,ht_away,ft_home,ft_away,status,match_date")
                .eq("status", "finished")
                .gte("match_date", f"{today}T00:00:00")
                .lte("match_date", f"{today}T23:59:59")
                .execute()
            )
            finished_matches = result.data or []
        except Exception:
            logger.exception("Biten maclar okunamadi.")
            return {"finished_matches": 0, "resolved_predictions": 0, "accuracy_pct": 0.0}

        resolved_total = 0
        correct_total = 0
        for match in finished_matches:
            score_data = {
                "ht_home": _safe_int(match.get("ht_home")),
                "ht_away": _safe_int(match.get("ht_away")),
                "ft_home": _safe_int(match.get("ft_home")),
                "ft_away": _safe_int(match.get("ft_away")),
            }
            stats = self._update_results_for_match(str(match.get("id")), score_data)
            resolved_total += stats["resolved"]
            correct_total += stats["correct"]

        accuracy = round((correct_total / resolved_total) * 100.0, 2) if resolved_total else 0.0
        pi_update = await self.refresh_pi_ratings()
        logger.info(
            "Gunluk sonuc gorevi tamamlandi. biten_mac=%s resolved=%s accuracy=%s%% pi_updated=%s",
            len(finished_matches),
            resolved_total,
            accuracy,
            pi_update.get("updated_teams", 0),
        )
        return {
            "finished_matches": len(finished_matches),
            "resolved_predictions": resolved_total,
            "correct_predictions": correct_total,
            "accuracy_pct": accuracy,
            "pi_rating_updated_teams": pi_update.get("updated_teams", 0),
        }

    async def update_weekly_team_stats(self) -> Dict[str, Any]:
        updated = 0
        league_rows: Dict[str, int] = {}
        for league_id in TRACKED_LEAGUE_IDS:
            standings = await self.api_service.get_standings(league_id, DEFAULT_SEASON)
            standings = standings or []
            league_rows[str(league_id)] = len(standings)
            for row in standings:
                team = row.get("team", {}) if isinstance(row.get("team"), dict) else {}
                team_id = _safe_int(team.get("id"))
                if team_id <= 0:
                    continue
                stats = await self.api_service.get_team_statistics(team_id, league_id, DEFAULT_SEASON)
                if stats:
                    updated += 1

        logger.info("Haftalik istatistik gorevi tamamlandi. updated_teams=%s", updated)
        return {"season": DEFAULT_SEASON, "updated_teams": updated, "league_rows": league_rows}

    async def fetch_sofascore_daily_events(self) -> Dict[str, Any]:
        dates = self._today_and_tomorrow()
        total = 0
        by_date: Dict[str, int] = {}
        for date_str in dates:
            rows = await self.sofascore.get_scheduled_events(date_str)
            count = len(rows or [])
            by_date[date_str] = count
            total += count
        logger.info("Sofascore gunluk gorevi tamamlandi. total=%s detay=%s", total, by_date)
        return {"total_events": total, "by_date": by_date}

    async def populate_today_team_stats_history(self) -> Dict[str, Any]:
        if self.supabase is None:
            return {"processed_matches": 0, "updated_teams": 0}

        today = datetime.now(self.timezone).date().isoformat()
        try:
            result = (
                self.supabase.table("matches")
                .select("id,match_date,status")
                .gte("match_date", f"{today}T00:00:00")
                .lte("match_date", f"{today}T23:59:59")
                .in_("status", ["scheduled", "live", "finished"])
                .order("match_date")
                .execute()
            )
            matches = result.data or []
        except Exception:
            logger.exception("populate_today_team_stats_history: today matches query failed.")
            return {"processed_matches": 0, "updated_teams": 0}

        processed = 0
        updated_teams = 0
        for row in matches:
            match_id = str(row.get("id") or "")
            if not match_id:
                continue
            response = await self.sofascore.populate_team_stats_for_match(match_id)
            if not response:
                continue
            processed += 1
            home_info = response.get("home", {}) if isinstance(response.get("home"), dict) else {}
            away_info = response.get("away", {}) if isinstance(response.get("away"), dict) else {}
            if int(home_info.get("updated_rows", 0) or 0) > 0:
                updated_teams += 1
            if int(away_info.get("updated_rows", 0) or 0) > 0:
                updated_teams += 1
            await asyncio.sleep(2)

        logger.info("Gunluk history team_stats gorevi tamamlandi. match=%s teams=%s", processed, updated_teams)
        return {"processed_matches": processed, "updated_teams": updated_teams}

    async def refresh_today_injuries_and_h2h(self) -> Dict[str, Any]:
        if self.supabase is None:
            return {"processed_matches": 0, "injury_rows": 0, "h2h_rows": 0}

        today = datetime.now(self.timezone).date().isoformat()
        tomorrow = (datetime.now(self.timezone).date() + timedelta(days=1)).isoformat()
        has_match_sofascore = self.sofascore._has_column("matches", "sofascore_id")
        select_columns = "id,match_date,status"
        if has_match_sofascore:
            select_columns += ",sofascore_id"
        try:
            result = (
                self.supabase.table("matches")
                .select(select_columns)
                .gte("match_date", f"{today}T00:00:00")
                .lte("match_date", f"{tomorrow}T23:59:59")
                .in_("status", ["scheduled", "live", "finished"])
                .order("match_date")
                .execute()
            )
            matches = result.data or []
        except Exception:
            logger.exception("refresh_today_injuries_and_h2h: match query failed.")
            return {"processed_matches": 0, "injury_rows": 0, "h2h_rows": 0}

        processed = 0
        injury_rows = 0
        h2h_rows = 0
        for row in matches:
            match_id = str(row.get("id") or "")
            if not match_id:
                continue
            event_id = _safe_int(row.get("sofascore_id")) if has_match_sofascore else 0
            if event_id <= 0:
                mapping = await self.sofascore._resolve_sofascore_team_ids_for_match(match_id)
                event_id = _safe_int(mapping.get("event_id")) if isinstance(mapping, dict) else 0
            if event_id <= 0:
                continue

            try:
                injuries = await self.sofascore.get_match_injuries(event_id)
                if isinstance(injuries, dict):
                    home_count = len(injuries.get("home", []) or [])
                    away_count = len(injuries.get("away", []) or [])
                    injury_rows += home_count + away_count
            except Exception:
                logger.exception("refresh_today_injuries_and_h2h: injuries failed. event_id=%s", event_id)

            try:
                h2h = await self.sofascore.get_h2h(event_id)
                if isinstance(h2h, dict) and isinstance(h2h.get("matches"), list):
                    h2h_rows += len(h2h.get("matches") or [])
            except Exception:
                logger.exception("refresh_today_injuries_and_h2h: h2h failed. event_id=%s", event_id)

            processed += 1
            await asyncio.sleep(0.5)

        logger.info(
            "Sofascore injuries+h2h gorevi tamamlandi. processed=%s injury_rows=%s h2h_rows=%s",
            processed,
            injury_rows,
            h2h_rows,
        )
        return {"processed_matches": processed, "injury_rows": injury_rows, "h2h_rows": h2h_rows}

    async def refresh_team_market_values(self) -> Dict[str, Any]:
        if self.supabase is None:
            return {"updated_teams": 0}
        try:
            result = self.supabase.table("teams").select("id,name").order("name").execute()
            teams = result.data or []
        except Exception:
            logger.exception("refresh_team_market_values: teams query failed.")
            return {"updated_teams": 0}

        updated = 0
        for team in teams:
            team_id = str(team.get("id") or "")
            team_name = str(team.get("name") or "").strip()
            if not team_id or not team_name:
                continue
            value = await self.transfermarkt.update_team_market_value(team_id, team_name)
            if value is not None and value > 0:
                updated += 1
            await asyncio.sleep(3)

        logger.info("Haftalik market value gorevi tamamlandi. updated_teams=%s", updated)
        return {"updated_teams": updated}

    async def refresh_pi_ratings(self) -> Dict[str, Any]:
        if self.supabase is None:
            return {"processed_matches": 0, "updated_teams": 0}
        return update_team_pi_ratings(self.supabase)

    def _extract_missing_players(self, lineups_payload: Optional[Dict[str, Any]]) -> int:
        if not isinstance(lineups_payload, dict):
            return 0
        home = lineups_payload.get("home", {}) if isinstance(lineups_payload.get("home"), dict) else {}
        away = lineups_payload.get("away", {}) if isinstance(lineups_payload.get("away"), dict) else {}
        home_missing = len(home.get("missingPlayers", [])) if isinstance(home.get("missingPlayers"), list) else 0
        away_missing = len(away.get("missingPlayers", [])) if isinstance(away.get("missingPlayers"), list) else 0
        return home_missing + away_missing

    def _extract_form_points(self, pregame_payload: Optional[Dict[str, Any]]) -> int:
        if not isinstance(pregame_payload, dict):
            return 0
        home = pregame_payload.get("homeTeam", {}) if isinstance(pregame_payload.get("homeTeam"), dict) else {}
        away = pregame_payload.get("awayTeam", {}) if isinstance(pregame_payload.get("awayTeam"), dict) else {}

        def points(raw: Any) -> int:
            if not isinstance(raw, list):
                return 0
            result = 0
            for item in raw[:5]:
                flag = str(item).upper()
                if flag == "W":
                    result += 3
                elif flag == "D":
                    result += 1
            return result

        return points(home.get("form")) - points(away.get("form"))

    def _extract_odds_signal(self, odds_payload: Optional[Dict[str, Any]]) -> int:
        if not isinstance(odds_payload, dict):
            return 0
        markets = odds_payload.get("markets", [])
        if not isinstance(markets, list):
            return 0
        return min(10, len(markets))

    def _save_sofascore_recalc_prediction(self, match_id: str, confidence: float, outcome: str) -> None:
        if self.supabase is None:
            return
        payload = {
            "match_id": match_id,
            "market_type": "SOFASCORE_RECALC",
            "predicted_outcome": outcome,
            "confidence_score": confidence,
            "ev_percentage": 0.0,
            "recommended": confidence >= 60.0,
        }
        try:
            existing = (
                self.supabase.table("predictions")
                .select("id")
                .eq("match_id", match_id)
                .eq("market_type", "SOFASCORE_RECALC")
                .limit(1)
                .execute()
            )
            if existing.data:
                self.supabase.table("predictions").update(payload).eq("id", existing.data[0]["id"]).execute()
            else:
                self.supabase.table("predictions").insert(payload).execute()
        except Exception:
            logger.exception("Sofascore recalc prediction save failed. match_id=%s", match_id)

    async def refresh_sofascore_two_hour_prematch(self) -> Dict[str, Any]:
        if self.supabase is None:
            return {"processed_matches": 0}
        now = datetime.now(self.timezone)
        lower_bound = (now + timedelta(minutes=95)).isoformat()
        upper_bound = (now + timedelta(minutes=145)).isoformat()
        has_match_sofascore = self.sofascore._has_column("matches", "sofascore_id")
        select_columns = "id,match_date,status"
        if has_match_sofascore:
            select_columns += ",sofascore_id"
        try:
            result = (
                self.supabase.table("matches")
                .select(select_columns)
                .eq("status", "scheduled")
                .gte("match_date", lower_bound)
                .lte("match_date", upper_bound)
                .order("match_date")
                .execute()
            )
            candidates = result.data or []
        except Exception:
            logger.exception("Sofascore pre-match adaylari okunamadi.")
            return {"processed_matches": 0}

        processed = 0
        injury_rows = 0
        h2h_rows = 0
        for row in candidates:
            match_id = str(row.get("id"))
            sofascore_id = _safe_int(row.get("sofascore_id")) if has_match_sofascore else 0
            if sofascore_id <= 0:
                mapping = await self.sofascore._resolve_sofascore_team_ids_for_match(match_id)
                sofascore_id = _safe_int(mapping.get("event_id")) if isinstance(mapping, dict) else 0
            if sofascore_id <= 0:
                continue

            lineups = await self.sofascore.get_event_lineups(sofascore_id)
            pregame = await self.sofascore.get_event_pregame_form(sofascore_id)
            odds = await self.sofascore.get_event_odds(sofascore_id)
            injuries = await self.sofascore.get_match_injuries(sofascore_id)
            h2h = await self.sofascore.get_h2h(sofascore_id)

            missing_players = self._extract_missing_players(lineups)
            form_gap = self._extract_form_points(pregame)
            odds_signal = self._extract_odds_signal(odds)
            if isinstance(injuries, dict):
                injury_rows += len(injuries.get("home", []) or []) + len(injuries.get("away", []) or [])
            if isinstance(h2h, dict) and isinstance(h2h.get("matches"), list):
                h2h_rows += len(h2h.get("matches") or [])

            confidence = 50.0
            confidence += max(-10.0, min(10.0, form_gap * 2.0))
            confidence += max(-8.0, 12.0 - missing_players * 2.0)
            confidence += min(8.0, odds_signal * 0.6)
            confidence = max(35.0, min(90.0, confidence))

            if form_gap > 0:
                outcome = "SOFASCORE_HOME_EDGE"
            elif form_gap < 0:
                outcome = "SOFASCORE_AWAY_EDGE"
            else:
                outcome = "SOFASCORE_BALANCED"
            self._save_sofascore_recalc_prediction(match_id, round(confidence, 2), outcome)

            processed += 1

        logger.info(
            "Sofascore pre-match gorevi tamamlandi. processed=%s injury_rows=%s h2h_rows=%s",
            processed,
            injury_rows,
            h2h_rows,
        )
        return {"processed_matches": processed, "injury_rows": injury_rows, "h2h_rows": h2h_rows}

    async def refresh_sofascore_odds(self) -> Dict[str, Any]:
        result = await self.odds_scraper.refresh_todays_matches(timezone_name="Europe/Istanbul")
        logger.info(
            "Sofascore odds gorevi tamamlandi. processed_matches=%s updated_markets=%s",
            result.get("processed_matches", 0),
            result.get("updated_markets", 0),
        )
        return result

    def configure(self) -> None:
        if self.scheduler.get_job("daily-fixtures"):
            return
        self.scheduler.add_job(
            self.fetch_today_and_tomorrow_fixtures,
            "cron",
            hour=6,
            minute=0,
            id="daily-fixtures",
            replace_existing=True,
        )
        self.scheduler.add_job(
            self.populate_today_team_stats_history,
            "cron",
            hour=7,
            minute=0,
            id="daily-team-stats-history",
            replace_existing=True,
        )
        self.scheduler.add_job(
            self.refresh_upcoming_odds,
            "interval",
            hours=3,
            id="odds-refresh-3h",
            replace_existing=True,
        )
        self.scheduler.add_job(
            self.reconcile_finished_matches,
            "cron",
            hour=23,
            minute=30,
            id="nightly-reconcile",
            replace_existing=True,
        )
        self.scheduler.add_job(
            self.update_weekly_team_stats,
            "cron",
            day_of_week="mon",
            hour=8,
            minute=0,
            id="weekly-stats",
            replace_existing=True,
        )
        self.scheduler.add_job(
            self.refresh_team_market_values,
            "cron",
            day_of_week="mon",
            hour=9,
            minute=0,
            id="weekly-market-values",
            replace_existing=True,
        )
        self.scheduler.add_job(
            self.fetch_sofascore_daily_events,
            "cron",
            hour=8,
            minute=0,
            id="sofascore-daily-events",
            replace_existing=True,
        )
        self.scheduler.add_job(
            self.refresh_today_injuries_and_h2h,
            "interval",
            hours=3,
            id="sofascore-injuries-h2h-3h",
            replace_existing=True,
        )
        self.scheduler.add_job(
            self.refresh_sofascore_two_hour_prematch,
            "interval",
            minutes=30,
            id="sofascore-prematch-2h",
            replace_existing=True,
        )
        self.scheduler.add_job(
            self.refresh_sofascore_odds,
            "interval",
            minutes=30,
            id="sofascore-odds-30m",
            replace_existing=True,
        )

    def start(self) -> None:
        if not self.scheduler.running:
            self.configure()
            self.scheduler.start()
            logger.info("Scheduler baslatildi.")

    async def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
        await self.api_service.close()
        await self.odds_tracker.close()
        await self.odds_scraper.close()
        await self.sofascore.close()
        await self.transfermarkt.close()
