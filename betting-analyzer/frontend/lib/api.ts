const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

export type DashboardMatch = {
  match_id: string;
  home_team: string;
  away_team: string;
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
      market_type: string;
      predicted_outcome: string;
      probability: number;
      odd: number;
      ev: number;
      ev_percentage: number;
      recommended: boolean;
    } | null;
    all_markets: Array<{
      market_type: string;
      predicted_outcome: string;
      probability: number;
      odd: number;
      ev: number;
      ev_percentage: number;
      recommended: boolean;
    }>;
  };
  recommended_market: {
    market_type: string;
    predicted_outcome: string;
    probability: number;
    odd: number;
    ev: number;
    ev_percentage: number;
    recommended: boolean;
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
    };
    away_team: {
      id: string;
      name: string;
      country?: string | null;
    };
  };
  form?: {
    home: Array<{ result: "W" | "D" | "L"; goals_scored: number; goals_conceded: number; updated_at: string }>;
    away: Array<{ result: "W" | "D" | "L"; goals_scored: number; goals_conceded: number; updated_at: string }>;
  };
  injuries?: Array<{
    team_id: number;
    team_name: string;
    player: string;
    reason: string;
    type: string;
  }>;
  h2h?: {
    summary: {
      home_wins?: number;
      away_wins?: number;
      draws?: number;
      ratio: number;
    };
    last5: Array<Record<string, unknown>>;
  };
  xg?: {
    home: number;
    away: number;
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
