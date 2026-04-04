function trimTrailingSlash(value: string): string {
  return value.replace(/\/$/, "");
}

function isLocalUrl(value: string): boolean {
  return /^https?:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/i.test(value);
}

function resolveBackendUrl(): string {
  const internalUrl = (process.env.BACKEND_INTERNAL_URL ?? "").trim();
  const serviceBackendUrl = (process.env.SERVICE_URL_BACKEND ?? "").trim();
  const publicUrl = (process.env.NEXT_PUBLIC_BACKEND_URL ?? "").trim();

  if (typeof window === "undefined") {
    if (internalUrl) {
      return trimTrailingSlash(internalUrl);
    }
    if (serviceBackendUrl) {
      return trimTrailingSlash(serviceBackendUrl);
    }
    if (publicUrl && !isLocalUrl(publicUrl)) {
      return trimTrailingSlash(publicUrl);
    }
    return "http://localhost:8000";
  }

  if (publicUrl && !isLocalUrl(publicUrl)) {
    return trimTrailingSlash(publicUrl);
  }

  return "/api/backend";
}

export type DashboardMatch = {
  match_id: string;
  home_team: string;
  away_team: string;
  home_logo_url?: string | null;
  away_logo_url?: string | null;
  league: string;
  match_date: string;
  market_type: string;
  confidence_score: number;
  ev_percentage: number;
  recommended: boolean;
  status: string;
};

export type MatchesTodayResponse = {
  count: number;
  tracked_leagues: number;
  matches: DashboardMatch[];
};

export type HistoryItem = {
  prediction_id: string;
  date: string;
  match_date: string;
  match: string;
  market_type: string;
  predicted_outcome: string;
  actual_outcome: string | null;
  was_correct: boolean | null;
  confidence_score: number;
  ev_percentage: number;
};

export type HistoryResponse = {
  count: number;
  items: HistoryItem[];
  summary: {
    total_predictions: number;
    correct_predictions: number;
    wrong_predictions: number;
    accuracy_percentage: number;
    weekly_accuracy_percentage: number;
    total_coupons: number;
  };
};

export type HealthResponse = {
  status: string;
  supabase_connected: boolean;
  scheduler: {
    running: boolean;
    jobs: Array<{ id: string; next_run_time: string | null }>;
  };
  api_football_remaining: number | null;
  the_odds_remaining: number | null;
  api_keys: {
    api_football: boolean;
    the_odds: boolean;
    openweather: boolean;
    supabase_service: boolean;
  };
  error: string | null;
  time: string;
};

export type MatchAnalysisResponse = {
  match_id: string;
  lambda?: {
    home: number;
    away: number;
    ht_home: number;
    ht_away: number;
  };
  confidence_score?: number;
  analysis: {
    confidence_score: number;
    recommended: boolean;
    criteria_scores: Record<string, number>;
  };
  ev: {
    confidence_score: number;
    confidence_threshold: number;
    recommended: boolean;
    best_market: {
      market?: string;
      market_type: string;
      predicted_outcome: string;
      probability: number;
      odd: number;
      ev: number;
      ev_percentage: number;
      recommended: boolean;
      kelly_pct?: number;
    } | null;
    all_markets: Array<{
      market?: string;
      market_type: string;
      predicted_outcome: string;
      probability: number;
      odd: number;
      ev: number;
      ev_percentage: number;
      recommended: boolean;
      kelly_pct?: number;
      suspicious_high_ev?: boolean;
    }>;
  };
  recommended_market: {
    market?: string;
    market_type: string;
    predicted_outcome: string;
    probability: number;
    odd: number;
    ev: number;
    ev_percentage: number;
    recommended: boolean;
    kelly_pct?: number;
  } | null;
  match?: {
    id: string;
    league: string;
    match_date: string;
    status: string;
    home_team: {
      id: string;
      name: string;
      country?: string | null;
      logo_url?: string | null;
    };
    away_team: {
      id: string;
      name: string;
      country?: string | null;
      logo_url?: string | null;
    };
  };
  form?: {
    home:
      | Array<{ result: "W" | "D" | "L"; goals_scored: number; goals_conceded: number; updated_at: string }>
      | {
          last6: Array<"W" | "D" | "L" | string>;
          score: number;
          matches: Array<{
            date: string;
            home_team_name: string;
            away_team_name: string;
            home_goals: number;
            away_goals: number;
            result: "W" | "D" | "L" | string;
            is_home: boolean;
          }>;
        };
    away:
      | Array<{ result: "W" | "D" | "L"; goals_scored: number; goals_conceded: number; updated_at: string }>
      | {
          last6: Array<"W" | "D" | "L" | string>;
          score: number;
          matches: Array<{
            date: string;
            home_team_name: string;
            away_team_name: string;
            home_goals: number;
            away_goals: number;
            result: "W" | "D" | "L" | string;
            is_home: boolean;
          }>;
        };
  };
  form_legacy?: {
    home: Array<{ result: "W" | "D" | "L"; goals_scored: number; goals_conceded: number; updated_at: string }>;
    away: Array<{ result: "W" | "D" | "L"; goals_scored: number; goals_conceded: number; updated_at: string }>;
  };
  injuries?:
    | Array<{
        team_id: string | number;
        team_name: string;
        player: string;
        reason: string;
        type: string;
      }>
    | {
        home: Array<{
          player_name: string;
          position?: string;
          status: string;
          reason?: string;
          expected_return?: string;
        }>;
        away: Array<{
          player_name: string;
          position?: string;
          status: string;
          reason?: string;
          expected_return?: string;
        }>;
      };
  injuries_flat?: Array<{
    team_id: string | number;
    team_name: string;
    player: string;
    player_name?: string;
    position?: string;
    reason?: string;
    type?: string;
    status?: string;
    expected_return?: string;
  }>;
  h2h?: {
    summary: {
      home_wins?: number;
      away_wins?: number;
      draws?: number;
      ratio: number;
      home_win_rate?: number;
    };
    matches?: Array<Record<string, unknown>>;
    last5?: Array<Record<string, unknown>>;
  };
  xg?: {
    home:
      | number
      | {
          attack_xg: number;
          defense_xg: number;
        };
    away:
      | number
      | {
          attack_xg: number;
          defense_xg: number;
        };
    legacy?: {
      home: number;
      away: number;
    };
  };
  sofascore?: {
    enabled?: boolean;
    event?: {
      event_id?: number;
      tournament_id?: number;
      tournament_name?: string;
      season_id?: number;
      season_name?: string;
    };
    standings?: Array<Record<string, unknown>>;
    season_team_stats?: {
      home?: Record<string, unknown>;
      away?: Record<string, unknown>;
    };
    top_players?: {
      home?: Array<Record<string, unknown>>;
      away?: Array<Record<string, unknown>>;
    };
  };
};

export type TeamDirectoryItem = {
  id: string;
  name: string;
  league: string;
  country: string;
  logo_url?: string | null;
  coach_name?: string | null;
  sofascore_id?: number | null;
  sofascore_team_url?: string | null;
  profile_sync_status?: string | null;
  profile_last_fetched_at?: string | null;
  slug?: string | null;
  team_status?: string | null;
};

export type TeamsResponse = {
  count: number;
  items: TeamDirectoryItem[];
};

export type TeamDetailResponse = {
  team: TeamDirectoryItem;
};

export type TeamOverviewStatItem = {
  key: string;
  label: string;
  value: string | number | boolean | null;
};

export type TeamOverviewStatGroup = {
  items: TeamOverviewStatItem[];
  values: Record<string, string | number | boolean | null>;
};

export type TeamOverviewMatch = {
  date: string;
  is_cup?: boolean;
  league?: string;
  result?: string;
  is_home?: boolean;
  event_id?: number;
  away_goals?: number;
  home_goals?: number;
  away_team_id?: number;
  home_team_id?: number;
  away_team_name?: string;
  home_team_name?: string;
};

export type TeamOverviewTournament = {
  tournament_id: number;
  season_id: number;
  tournament_name?: string;
  season_name?: string;
  last_five_matches: TeamOverviewMatch[];
  form_last_ten: {
    wins: number;
    draws: number;
    losses: number;
    points: number;
    results: string[];
    score_pct: number;
  };
  summary_stats: TeamOverviewStatGroup;
  attack_stats: TeamOverviewStatGroup;
  passing_stats: TeamOverviewStatGroup;
  defending_stats: TeamOverviewStatGroup;
  other_stats: TeamOverviewStatGroup;
  updated_at: string;
};

export type TeamOverviewResponse = {
  team: TeamDirectoryItem & {
    team_data_sync_status?: string | null;
    team_data_last_fetched_at?: string | null;
    team_data_last_error?: string | null;
  };
  recent_matches: TeamOverviewMatch[];
  form_last_ten: {
    wins: number;
    draws: number;
    losses: number;
    points: number;
    results: string[];
    score_pct: number;
  };
  default_tournament?: {
    tournament_id: number;
    season_id: number;
  } | null;
  tournaments: TeamOverviewTournament[];
};

export type TeamComparisonMetaResponse = {
  default_scope: string;
  default_data_window: number;
  default_robot: string;
  model_version: string;
  supported_scopes: string[];
  supported_windows: number[];
  supported_robots: string[];
  team_selector_source: string;
  featured_teams: Array<{
    id: string;
    name: string;
    league: string;
    country: string;
  }>;
};

export type TeamComparisonCard = {
  key: string;
  label: string;
  home_score: number;
  away_score: number;
  edge: number;
  winner: "home" | "away" | "draw";
  winner_label: string;
  explanation: string;
};

export type TeamComparisonScenario = {
  key: string;
  title: string;
  probability_score: number;
  favored_side: string;
  reasons: string[];
  risk_factors: string[];
  first_goal_window: string;
  tempo: string;
};

export type TeamComparisonScoreline = {
  score: string;
  home_goals: number;
  away_goals: number;
  probability: number;
};

export type TeamComparisonRobotOutput = {
  name: string;
  spec_version: string;
  methodology: string;
  key_signals: string[];
  model_breakdown: Array<{
    label: string;
    home_value: number;
    away_value: number;
    winner: string;
    winner_label: string;
    edge: number;
  }>;
  report_blocks: Array<{
    title: string;
    body: string;
  }>;
  summary_card: {
    favorite_team: string;
    power_difference_pct: number;
    recommended_scenario: string;
    most_likely_score: string;
    confidence_label: string;
    risk_warning: string;
  };
  confidence_note: string;
  data_gaps: string[];
};

export type TeamComparisonResponse = {
  request: {
    home_team_id: string;
    away_team_id: string;
    scope: string;
    data_window: number;
    season_mode: string;
    tournament_id?: number | null;
    season_id?: number | null;
    date_from?: string | null;
    date_to?: string | null;
    refresh: boolean;
  };
  header_summary: {
    home_team: TeamDirectoryItem;
    away_team: TeamDirectoryItem;
    league_context: string;
    comparison_date: string;
    data_window: number;
    confidence_score: number;
    data_quality_score: number;
    cross_league: boolean;
    fixture_context?: Record<string, unknown>;
  };
  shared_comparison: {
    cards: TeamComparisonCard[];
    axes: TeamComparisonCard[];
    comparison_edge: number;
  };
  probability_block: {
    home_edge: number;
    draw_tendency: number;
    away_threat_level: number;
    over_tendency: number;
    btts_tendency: number;
    top_5_scorelines: TeamComparisonScoreline[];
    top_3_scenarios: TeamComparisonScenario[];
    one_x_two: {
      home: number;
      draw: number;
      away: number;
    };
    totals: {
      over_1_5: number;
      under_1_5: number;
      over_2_5: number;
      under_2_5: number;
      over_3_5: number;
      under_3_5: number;
    };
    btts: {
      yes: number;
      no: number;
    };
    lambda_home: number;
    lambda_away: number;
    tempo_class: string;
    first_goal_window: string;
  };
  visualization: {
    radar_values: {
      home: Record<string, number>;
      away: Record<string, number>;
    };
    bar_comparison: TeamComparisonCard[];
    scenario_bars: TeamComparisonScenario[];
  };
  robots: {
    ana: TeamComparisonRobotOutput;
    bma: TeamComparisonRobotOutput;
    gma: TeamComparisonRobotOutput;
  };
  data_quality: {
    score: number;
    components: Record<string, number>;
  };
  confidence: {
    confidence_score: number;
    data_quality_score: number;
    confidence_band: string;
    components: Record<string, number>;
    warnings: string[];
  };
  data_gaps: string[];
  meta: {
    model_version: string;
    cache_hit: boolean;
    selected_tournament?: {
      tournament_id?: number;
      season_id?: number;
      tournament_name?: string;
      season_name?: string;
    } | null;
    feature_sources: Record<string, string>;
    included_match_ids: string[];
  };
};

export type CouponSelectionPayload = {
  match_id: string;
  home_team: string;
  away_team: string;
  market_type: string;
  odd: number;
  confidence_score: number;
  ev_percentage: number;
};

export type BacktestDatasetPreviewRow = {
  match_id: string;
  match_date: string;
  league: string;
  home_team: string;
  away_team: string;
  score: string;
  has_odds: boolean;
};

export type BacktestDatasetResponse = {
  window: {
    start_date: string;
    end_date: string;
    days_back: number;
  };
  league_filter: string;
  total_matches_scanned: number;
  matches_with_odds: number;
  preview_count: number;
  preview: BacktestDatasetPreviewRow[];
};

export type BacktestRunRequest = {
  start_date?: string;
  end_date?: string;
  days_back?: number;
  league?: string;
  min_confidence?: number;
  include_non_recommended?: boolean;
  max_matches?: number;
  store_rows?: number;
};

export type BacktestResultRow = {
  match_id: string;
  date: string;
  league: string;
  home_team: string;
  away_team: string;
  score: string;
  our_market: string;
  our_probability: number;
  our_odd: number;
  our_ev: number;
  confidence_score: number;
  recommended: boolean;
  reject_reason?: string | null;
  kelly_pct: number;
  hit: boolean | null;
  profit_units: number;
  meta?: Record<string, unknown>;
};

export type BacktestStatusResponse = {
  status: string;
  running: boolean;
  started_at: string | null;
  finished_at: string | null;
  params: Record<string, unknown> | null;
  processed: number;
  total_matches_scanned: number;
  success: number;
  failed: number;
  skipped_no_odds: number;
  skipped_no_market: number;
  summary: {
    total_predictions: number;
    evaluated_predictions: number;
    hits: number;
    misses: number;
    unresolved: number;
    hit_rate_pct: number;
    avg_ev: number;
    total_pnl_units: number;
    roi_pct: number;
    by_market: Array<{
      market: string;
      count: number;
      hits: number;
      misses: number;
      hit_rate_pct: number;
    }>;
  } | null;
  rows: BacktestResultRow[];
  last_error: string | null;
};

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const backendUrl = resolveBackendUrl();
  const response = await fetch(`${backendUrl}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {})
    },
    cache: "no-store"
  });
  if (!response.ok) {
    const text = await response.text();
    const fallback = `HTTP ${response.status}`;
    let detail = text.trim() || fallback;

    try {
      const parsed = JSON.parse(text) as { detail?: unknown };
      if (typeof parsed?.detail === "string" && parsed.detail.trim()) {
        detail = parsed.detail.trim();
      }
    } catch {
      // Keep original text when not JSON.
    }

    const normalized = detail.toLowerCase();
    const isBackendUnavailable =
      response.status >= 500 &&
      (normalized.includes("backend proxy") ||
        normalized.includes("upstream") ||
        normalized.includes("fetch failed") ||
        normalized.includes("service unavailable") ||
        normalized.includes("not configured"));

    if (isBackendUnavailable) {
      throw new Error("Backend servisine su an ulasilamiyor. Lutfen daha sonra tekrar deneyin.");
    }

    if (detail.startsWith("<!DOCTYPE")) {
      throw new Error(fallback);
    }

    throw new Error(detail);
  }
  return (await response.json()) as T;
}

export async function getTodayMatches(minConfidence: number): Promise<MatchesTodayResponse> {
  return fetchJson<MatchesTodayResponse>(`/matches/today?min_confidence=${minConfidence}`);
}

export async function getMatchAnalysis(matchId: string): Promise<MatchAnalysisResponse> {
  return fetchJson<MatchAnalysisResponse>(`/matches/${matchId}/analysis`);
}

export async function getHistory(params?: {
  startDate?: string;
  endDate?: string;
  marketType?: string;
  correct?: string;
}): Promise<HistoryResponse> {
  const search = new URLSearchParams();
  if (params?.startDate) {
    search.set("start_date", params.startDate);
  }
  if (params?.endDate) {
    search.set("end_date", params.endDate);
  }
  if (params?.marketType && params.marketType !== "all") {
    search.set("market_type", params.marketType);
  }
  if (params?.correct && params.correct !== "all") {
    search.set("correct", params.correct);
  }
  const query = search.toString();
  return fetchJson<HistoryResponse>(`/history${query ? `?${query}` : ""}`);
}

export async function getHealth(): Promise<HealthResponse> {
  return fetchJson<HealthResponse>("/health");
}

export async function getTeams(params?: {
  league?: string;
  country?: string;
  q?: string;
  limit?: number;
  offset?: number;
}): Promise<TeamsResponse> {
  const search = new URLSearchParams();
  if (params?.league) {
    search.set("league", params.league);
  }
  if (params?.country) {
    search.set("country", params.country);
  }
  if (params?.q) {
    search.set("q", params.q);
  }
  if (typeof params?.limit === "number") {
    search.set("limit", String(params.limit));
  }
  if (typeof params?.offset === "number") {
    search.set("offset", String(params.offset));
  }
  const query = search.toString();
  return fetchJson<TeamsResponse>(`/teams${query ? `?${query}` : ""}`);
}

export async function getTeam(teamId: string): Promise<TeamDetailResponse> {
  return fetchJson<TeamDetailResponse>(`/teams/${teamId}`);
}

export async function getTeamOverview(teamId: string): Promise<TeamOverviewResponse> {
  return fetchJson<TeamOverviewResponse>(`/teams/${teamId}/overview`);
}

export async function getTeamComparisonMeta(): Promise<TeamComparisonMetaResponse> {
  return fetchJson<TeamComparisonMetaResponse>("/team-comparison/meta");
}

export async function getTeamComparison(params: {
  homeTeamId: string;
  awayTeamId: string;
  scope?: string;
  dataWindow?: number;
  seasonMode?: string;
  tournamentId?: number;
  seasonId?: number;
  dateFrom?: string;
  dateTo?: string;
  refresh?: boolean;
}): Promise<TeamComparisonResponse> {
  const search = new URLSearchParams();
  search.set("home_team_id", params.homeTeamId);
  search.set("away_team_id", params.awayTeamId);
  if (params.scope) {
    search.set("scope", params.scope);
  }
  if (params.dataWindow) {
    search.set("data_window", String(params.dataWindow));
  }
  if (params.seasonMode) {
    search.set("season_mode", params.seasonMode);
  }
  if (typeof params.tournamentId === "number") {
    search.set("tournament_id", String(params.tournamentId));
  }
  if (typeof params.seasonId === "number") {
    search.set("season_id", String(params.seasonId));
  }
  if (params.dateFrom) {
    search.set("date_from", params.dateFrom);
  }
  if (params.dateTo) {
    search.set("date_to", params.dateTo);
  }
  if (params.refresh) {
    search.set("refresh", "true");
  }
  return fetchJson<TeamComparisonResponse>(`/team-comparison?${search.toString()}`);
}

export async function createCoupon(selections: CouponSelectionPayload[]): Promise<{
  coupon_id: string;
  status: string;
  total_odds: number;
  selections_count: number;
}> {
  const totalOdds = selections.reduce((acc, item) => acc * item.odd, 1);
  return fetchJson("/coupons", {
    method: "POST",
    body: JSON.stringify({
      selections,
      total_odds: Number(totalOdds.toFixed(3)),
      status: "pending"
    })
  });
}

export async function triggerFetchToday(): Promise<{ status: string; date: string }> {
  return fetchJson("/tasks/fetch-today", { method: "POST" });
}

export async function triggerUpdateStats(): Promise<{ status: string }> {
  return fetchJson("/tasks/update-stats", { method: "POST" });
}

export async function getBacktestDataset(params: {
  daysBack?: number;
  startDate?: string;
  endDate?: string;
  league?: string;
  maxMatches?: number;
  previewLimit?: number;
}): Promise<BacktestDatasetResponse> {
  const search = new URLSearchParams();
  if (typeof params.daysBack === "number") {
    search.set("days_back", String(params.daysBack));
  }
  if (params.startDate) {
    search.set("start_date", params.startDate);
  }
  if (params.endDate) {
    search.set("end_date", params.endDate);
  }
  if (params.league) {
    search.set("league", params.league);
  }
  if (typeof params.maxMatches === "number") {
    search.set("max_matches", String(params.maxMatches));
  }
  if (typeof params.previewLimit === "number") {
    search.set("preview_limit", String(params.previewLimit));
  }
  const query = search.toString();
  return fetchJson<BacktestDatasetResponse>(`/admin/backtest/dataset${query ? `?${query}` : ""}`);
}

export async function startBacktestRun(payload: BacktestRunRequest): Promise<{
  status: string;
  message: string;
  params: Record<string, unknown>;
}> {
  return fetchJson("/admin/backtest/run", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function getBacktestStatus(): Promise<BacktestStatusResponse> {
  return fetchJson<BacktestStatusResponse>("/admin/backtest/status");
}
