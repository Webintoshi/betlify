const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL ?? "/api/backend";

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

export type CouponSelectionPayload = {
  match_id: string;
  home_team: string;
  away_team: string;
  market_type: string;
  odd: number;
  confidence_score: number;
  ev_percentage: number;
};

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BACKEND_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {})
    },
    cache: "no-store"
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
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
