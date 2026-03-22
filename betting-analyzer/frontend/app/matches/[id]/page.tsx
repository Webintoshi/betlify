"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardTitle, CardHeader, CardContent } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { addCouponSelection } from "@/lib/coupon-store";
import { getMatchAnalysis, type MatchAnalysisResponse } from "@/lib/api";
import { formatDateTime, initials, toPercent } from "@/lib/utils";
import { cn } from "@/lib/utils";

function RadarChart({ scores }: { scores: Record<string, number> }) {
  const labels = Object.keys(scores);
  const values = labels.map((label) => scores[label] ?? 0);
  const size = 280;
  const center = size / 2;
  const radius = 95;
  const steps = 5;
  const angleStep = (Math.PI * 2) / Math.max(labels.length, 1);

  const polygonPoints = values
    .map((value, index) => {
      const ratio = Math.max(0, Math.min(100, value)) / 100;
      const angle = -Math.PI / 2 + index * angleStep;
      const x = center + Math.cos(angle) * radius * ratio;
      const y = center + Math.sin(angle) * radius * ratio;
      return `${x},${y}`;
    })
    .join(" ");

  return (
    <div className="overflow-x-auto">
      <svg width={size} height={size} className="mx-auto">
        {Array.from({ length: steps }).map((_, stepIndex) => {
          const stepRadius = (radius / steps) * (stepIndex + 1);
          const points = labels
            .map((_, index) => {
              const angle = -Math.PI / 2 + index * angleStep;
              const x = center + Math.cos(angle) * stepRadius;
              const y = center + Math.sin(angle) * stepRadius;
              return `${x},${y}`;
            })
            .join(" ");
          return (
            <polygon
              key={stepIndex}
              points={points}
              fill="none"
              stroke="rgba(255,255,255,0.06)"
              strokeWidth="1"
            />
          );
        })}

        {labels.map((label, index) => {
          const angle = -Math.PI / 2 + index * angleStep;
          const x = center + Math.cos(angle) * radius;
          const y = center + Math.sin(angle) * radius;
          const tx = center + Math.cos(angle) * (radius + 22);
          const ty = center + Math.sin(angle) * (radius + 22);
          return (
            <g key={label}>
              <line
                x1={center}
                y1={center}
                x2={x}
                y2={y}
                stroke="rgba(255,255,255,0.06)"
                strokeWidth="1"
              />
              <text
                x={tx}
                y={ty}
                textAnchor="middle"
                className="fill-foreground-muted text-[9px] font-medium"
              >
                {label}
              </text>
            </g>
          );
        })}

        <polygon
          points={polygonPoints}
          fill="url(#radarGradient)"
          stroke="#6366f1"
          strokeWidth="2"
        />
        
        <defs>
          <linearGradient id="radarGradient" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="rgba(99, 102, 241, 0.4)" />
            <stop offset="100%" stopColor="rgba(139, 92, 246, 0.2)" />
          </linearGradient>
        </defs>
      </svg>
    </div>
  );
}

function formColor(result: "W" | "D" | "L"): string {
  if (result === "W") {
    return "bg-success/20 text-success border-success/30";
  }
  if (result === "D") {
    return "bg-warning/20 text-warning border-warning/30";
  }
  return "bg-error/20 text-error border-error/30";
}

function FormBadge({ result }: { result: "W" | "D" | "L" }) {
  const labels = { W: "G", D: "B", L: "M" };
  return (
    <span
      className={cn(
        "inline-flex items-center justify-center w-8 h-8 rounded-lg text-xs font-bold border",
        formColor(result)
      )}
    >
      {labels[result]}
    </span>
  );
}

function normalizeResult(value: unknown): "W" | "D" | "L" {
  const token = String(value ?? "").toUpperCase();
  if (token === "W" || token === "D") {
    return token;
  }
  return "L";
}

function toNumber(value: unknown, fallback = 0): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function formatMetric(value: number, digits = 1): string {
  return Number.isFinite(value) ? value.toFixed(digits) : "0.0";
}

function normalizeName(value: string): string {
  return String(value ?? "")
    .toLowerCase()
    .replace(/[^a-z0-9]/g, "");
}

function TeamAvatar({ name, logoUrl }: { name: string; logoUrl?: string | null }) {
  const [imageError, setImageError] = useState<boolean>(false);
  const normalizedLogo = typeof logoUrl === "string" ? logoUrl.trim() : "";
  const showLogo = Boolean(normalizedLogo) && !imageError;
  return (
    <div className="flex flex-col items-center gap-3">
      <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-accent/20 to-accent-secondary/10 border border-accent/20 flex items-center justify-center">
        {showLogo ? (
          <img
            src={normalizedLogo}
            alt={`${name} logo`}
            className="h-12 w-12 object-contain"
            loading="lazy"
            onError={() => setImageError(true)}
          />
        ) : (
          <span className="text-lg font-bold text-foreground-primary">
            {initials(name)}
          </span>
        )}
      </div>
      <span className="text-sm font-semibold text-foreground-primary text-center max-w-[120px]">
        {name}
      </span>
    </div>
  );
}

function SofaScoreLineupsEmbed({ eventId }: { eventId: number }) {
  const iframeSrc = `https://widgets.sofascore.com/tr/embed/lineups?id=${eventId}&widgetTheme=dark`;
  const matchUrl = `https://www.sofascore.com/tr/event/${eventId}`;

  return (
    <Card className="overflow-hidden border-accent/30 bg-gradient-to-b from-accent/5 to-transparent">
      <CardHeader>
        <div className="flex items-center justify-between gap-2">
          <CardTitle>SofaScore Kadrolar</CardTitle>
          <Badge variant="accent" size="sm">CanlÄ± Widget</Badge>
        </div>
        <CardDescription>MaÃ§ kadrolarÄ± ve diziliÅŸler (SofaScore)</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="overflow-hidden rounded-xl border border-white/[0.08] bg-[#0b1220]">
          <iframe
            id={`sofa-lineups-embed-${eventId}`}
            title={`SofaScore lineups ${eventId}`}
            src={iframeSrc}
            className="mx-auto block w-full"
            style={{ height: "786px", maxWidth: "800px" }}
            frameBorder={0}
            scrolling="no"
            loading="lazy"
          />
        </div>
        <p className="text-xs text-foreground-muted">
          <a href={matchUrl} target="_blank" rel="noreferrer" className="text-accent hover:underline">
            SofaScore Ã¼zerinde maÃ§ detayÄ±nÄ± aÃ§
          </a>
        </p>
      </CardContent>
    </Card>
  );
}

export default function MatchDetailsPage() {
  const params = useParams<{ id: string }>();
  const matchId = typeof params?.id === "string" ? params.id : "";
  const [data, setData] = useState<MatchAnalysisResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string>("");
  const [saved, setSaved] = useState<boolean>(false);
  const [isClient, setIsClient] = useState<boolean>(false);

  useEffect(() => {
    setIsClient(true);
  }, []);

  useEffect(() => {
    if (!matchId) {
      setLoading(false);
      setError("Maç kimliği bulunamadı.");
      return;
    }
    const load = async () => {
      setLoading(true);
      setError("");
      try {
        const response = await getMatchAnalysis(matchId);
        setData(response);
      } catch (requestError) {
        setError(requestError instanceof Error ? requestError.message : "Maç analizi alınamadı.");
      } finally {
        setLoading(false);
      }
    };
    void load();
  }, [matchId]);

  const criteriaScores = useMemo(() => data?.analysis?.criteria_scores ?? {}, [data]);
  const allMarkets = useMemo(
    () => (Array.isArray(data?.ev?.all_markets) ? data.ev.all_markets : []),
    [data]
  );
  const homeFormItems = useMemo(() => {
    const homeForm = data?.form?.home;
    if (Array.isArray(homeForm)) {
      return homeForm.map((item) => ({ result: normalizeResult(item.result) }));
    }
    if (homeForm && typeof homeForm === "object" && Array.isArray(homeForm.last6)) {
      return homeForm.last6.map((item) => ({ result: normalizeResult(item) }));
    }
    if (Array.isArray(data?.form_legacy?.home)) {
      return data.form_legacy.home.map((item) => ({ result: normalizeResult(item.result) }));
    }
    return [];
  }, [data]);
  const awayFormItems = useMemo(() => {
    const awayForm = data?.form?.away;
    if (Array.isArray(awayForm)) {
      return awayForm.map((item) => ({ result: normalizeResult(item.result) }));
    }
    if (awayForm && typeof awayForm === "object" && Array.isArray(awayForm.last6)) {
      return awayForm.last6.map((item) => ({ result: normalizeResult(item) }));
    }
    if (Array.isArray(data?.form_legacy?.away)) {
      return data.form_legacy.away.map((item) => ({ result: normalizeResult(item.result) }));
    }
    return [];
  }, [data]);
  const injuriesFlat = useMemo(() => {
    if (Array.isArray(data?.injuries)) {
      return data.injuries;
    }
    if (Array.isArray(data?.injuries_flat)) {
      return data.injuries_flat;
    }
    if (data?.injuries && typeof data.injuries === "object") {
      const homeRows = Array.isArray(data.injuries.home) ? data.injuries.home : [];
      const awayRows = Array.isArray(data.injuries.away) ? data.injuries.away : [];
      const home = homeRows.map((row) => ({
        team_name: data.match?.home_team.name ?? "Ev Sahibi",
        player: row.player_name,
        reason: row.reason ?? "",
        type: row.status ?? "injured"
      }));
      const away = awayRows.map((row) => ({
        team_name: data.match?.away_team.name ?? "Deplasman",
        player: row.player_name,
        reason: row.reason ?? "",
        type: row.status ?? "injured"
      }));
      return [...home, ...away];
    }
    return [];
  }, [data]);
  const h2hMatches = useMemo(() => {
    const fromMatches = data?.h2h?.matches;
    if (Array.isArray(fromMatches) && fromMatches.length > 0) {
      return fromMatches;
    }
    return Array.isArray(data?.h2h?.last5) ? data.h2h.last5 : [];
  }, [data]);
  const homeAttackXg = useMemo(() => {
    const home = data?.xg?.home;
    if (typeof home === "number") {
      return toNumber(home, 0);
    }
    return toNumber(home?.attack_xg ?? data?.xg?.legacy?.home, 0);
  }, [data]);
  const homeDefenseXg = useMemo(() => {
    const home = data?.xg?.home;
    if (typeof home === "number") {
      return 0;
    }
    return toNumber(home?.defense_xg, 0);
  }, [data]);
  const awayAttackXg = useMemo(() => {
    const away = data?.xg?.away;
    if (typeof away === "number") {
      return toNumber(away, 0);
    }
    return toNumber(away?.attack_xg ?? data?.xg?.legacy?.away, 0);
  }, [data]);
  const awayDefenseXg = useMemo(() => {
    const away = data?.xg?.away;
    if (typeof away === "number") {
      return 0;
    }
    return toNumber(away?.defense_xg, 0);
  }, [data]);
  const sofascoreEventId = useMemo(() => {
    const rawEventId = data?.sofascore?.event?.event_id;
    const parsed = Number(rawEventId ?? 0);
    return Number.isFinite(parsed) && parsed > 0 ? parsed : 0;
  }, [data]);
  const sofascoreSeasonHome = useMemo(() => {
    const raw = data?.sofascore?.season_team_stats?.home;
    return raw && typeof raw === "object" ? (raw as Record<string, unknown>) : null;
  }, [data]);
  const sofascoreSeasonAway = useMemo(() => {
    const raw = data?.sofascore?.season_team_stats?.away;
    return raw && typeof raw === "object" ? (raw as Record<string, unknown>) : null;
  }, [data]);
  const seasonComparisonRows = useMemo(() => {
    const homePlayed = toNumber(sofascoreSeasonHome?.matches_played, 0);
    const awayPlayed = toNumber(sofascoreSeasonAway?.matches_played, 0);
    return [
      {
        key: "avg_rating",
        label: "Ortalama Reyting",
        home: toNumber(sofascoreSeasonHome?.avg_rating, 0),
        away: toNumber(sofascoreSeasonAway?.avg_rating, 0),
        digits: 2,
        suffix: "",
      },
      {
        key: "matches",
        label: "Maclar",
        home: homePlayed,
        away: awayPlayed,
        digits: 0,
        suffix: "",
      },
      {
        key: "goals",
        label: "Atilan Gol",
        home: toNumber(sofascoreSeasonHome?.goals_for, 0),
        away: toNumber(sofascoreSeasonAway?.goals_for, 0),
        digits: 0,
        suffix: "",
      },
      {
        key: "goals_per_match",
        label: "Mac Basina Gol",
        home: toNumber(sofascoreSeasonHome?.goals_per_match, 0),
        away: toNumber(sofascoreSeasonAway?.goals_per_match, 0),
        digits: 1,
        suffix: "",
      },
      {
        key: "conceded",
        label: "Yenilen Gol",
        home: toNumber(sofascoreSeasonHome?.goals_against, 0),
        away: toNumber(sofascoreSeasonAway?.goals_against, 0),
        digits: 0,
        suffix: "",
      },
      {
        key: "clean_sheets",
        label: "Gol Yemedi",
        home: toNumber(sofascoreSeasonHome?.clean_sheets, 0),
        away: toNumber(sofascoreSeasonAway?.clean_sheets, 0),
        digits: 0,
        suffix: "",
      },
      {
        key: "assists",
        label: "Asist",
        home: toNumber(sofascoreSeasonHome?.assists, 0),
        away: toNumber(sofascoreSeasonAway?.assists, 0),
        digits: 0,
        suffix: "",
      },
      {
        key: "possession",
        label: "Topla Oynama",
        home: toNumber(sofascoreSeasonHome?.possession, 0),
        away: toNumber(sofascoreSeasonAway?.possession, 0),
        digits: 1,
        suffix: "%",
      },
    ];
  }, [sofascoreSeasonHome, sofascoreSeasonAway]);
  const homeTopPlayers = useMemo<Array<Record<string, unknown>>>(() => {
    const rows = data?.sofascore?.top_players?.home;
    return Array.isArray(rows) ? (rows as Array<Record<string, unknown>>) : [];
  }, [data]);
  const awayTopPlayers = useMemo<Array<Record<string, unknown>>>(() => {
    const rows = data?.sofascore?.top_players?.away;
    return Array.isArray(rows) ? (rows as Array<Record<string, unknown>>) : [];
  }, [data]);
  const standingsRows = useMemo(() => {
    const rows = data?.sofascore?.standings;
    return Array.isArray(rows) ? (rows as Array<Record<string, unknown>>) : [];
  }, [data]);
  const homeStanding = useMemo(() => {
    if (!data?.match) {
      return null;
    }
    const expectedId = toNumber(sofascoreSeasonHome?.team_sofascore_id, 0);
    const expectedName = normalizeName(data.match.home_team.name);
    return (
      standingsRows.find((row) => {
        const rowId = toNumber(row.team_sofascore_id, 0);
        const rowName = normalizeName(String(row.team_name ?? ""));
        return (expectedId > 0 && rowId === expectedId) || (expectedName.length > 0 && rowName === expectedName);
      }) ?? null
    );
  }, [standingsRows, data, sofascoreSeasonHome]);
  const awayStanding = useMemo(() => {
    if (!data?.match) {
      return null;
    }
    const expectedId = toNumber(sofascoreSeasonAway?.team_sofascore_id, 0);
    const expectedName = normalizeName(data.match.away_team.name);
    return (
      standingsRows.find((row) => {
        const rowId = toNumber(row.team_sofascore_id, 0);
        const rowName = normalizeName(String(row.team_name ?? ""));
        return (expectedId > 0 && rowId === expectedId) || (expectedName.length > 0 && rowName === expectedName);
      }) ?? null
    );
  }, [standingsRows, data, sofascoreSeasonAway]);
  const hasSeasonStats = useMemo(
    () => seasonComparisonRows.some((row) => toNumber(row.home, 0) > 0 || toNumber(row.away, 0) > 0),
    [seasonComparisonRows]
  );
  const hasTopPlayers = homeTopPlayers.length > 0 || awayTopPlayers.length > 0;
  const hasStandings = Boolean(homeStanding || awayStanding);
  const showSofascoreInsights = hasSeasonStats || hasTopPlayers || hasStandings;

  const handleAddCoupon = () => {
    if (!data?.match || !data.recommended_market) {
      return;
    }
    addCouponSelection({
      match_id: data.match.id,
      home_team: data.match.home_team.name,
      away_team: data.match.away_team.name,
      market_type: data.recommended_market.market_type,
      odd: data.recommended_market.odd,
      confidence_score: data.analysis.confidence_score,
      ev_percentage: data.recommended_market.ev_percentage
    });
    setSaved(true);
    window.setTimeout(() => setSaved(false), 1800);
  };

  if (!isClient || loading) {
    return (
      <section className="flex items-center justify-center min-h-[60vh]">
        <div className="flex flex-col items-center gap-4">
          <svg className="animate-spin h-8 w-8 text-accent" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
          </svg>
          <p className="text-sm text-foreground-tertiary">Maç analizi yükleniyor...</p>
        </div>
      </section>
    );
  }

  if (error) {
    return (
      <section className="space-y-6 animate-fade-in">
        <div className="rounded-2xl bg-error/10 border border-error/20 p-6 flex items-start gap-4">
          <div className="w-12 h-12 rounded-xl bg-error/20 flex items-center justify-center flex-shrink-0">
            <svg className="w-6 h-6 text-error" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
          <div>
            <h2 className="text-lg font-semibold text-error mb-1">Analiz Yüklenemedi</h2>
            <p className="text-sm text-error/70">{error}</p>
          </div>
        </div>
      </section>
    );
  }

  if (!data?.match) {
    return (
      <section className="space-y-6 animate-fade-in">
        <div className="rounded-2xl bg-warning/10 border border-warning/20 p-6 text-center">
          <p className="text-foreground-secondary">Maç verisi bulunamadı.</p>
        </div>
      </section>
    );
  }

  return (
    <section className="space-y-6 animate-fade-in">
      {/* Header */}
      <div>
        <div className="flex items-center gap-3 mb-2">
          <Badge variant="accent" size="sm">Maç Detay</Badge>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-foreground-muted">
            Betlify
          </p>
        </div>
        <h1 className="text-display-sm text-foreground-primary">
          Analiz Ekranı
        </h1>
      </div>

      {/* Match Header */}
      <Card variant="accent" className="overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-br from-accent/5 via-transparent to-accent-secondary/5 pointer-events-none" />
        <CardContent className="relative">
          <div className="flex flex-col items-center gap-6 py-4">
            {/* League & Date */}
            <div className="flex flex-col items-center gap-2">
              <Badge variant="accent" size="md">
                🏆 {data.match.league}
              </Badge>
              <p className="text-sm text-foreground-tertiary">
                {formatDateTime(data.match.match_date)}
              </p>
            </div>

            {/* Teams */}
            <div className="flex items-center gap-8 sm:gap-16">
              <TeamAvatar
                name={data.match.home_team.name}
                logoUrl={data.match.home_team.logo_url}
              />
              
              <div className="flex flex-col items-center gap-2">
                <span className="text-3xl font-bold text-foreground-muted">VS</span>
                {data.analysis.recommended ? (
                  <Badge variant="success" size="sm" dot>Önerilir</Badge>
                ) : (
                  <Badge variant="warning" size="sm" dot>Sınırda</Badge>
                )}
              </div>
              
              <TeamAvatar
                name={data.match.away_team.name}
                logoUrl={data.match.away_team.logo_url}
              />
            </div>
          </div>
        </CardContent>
      </Card>

      {sofascoreEventId > 0 ? <SofaScoreLineupsEmbed eventId={sofascoreEventId} /> : null}

      {showSofascoreInsights ? (
        <Card className="overflow-hidden border-accent/20">
          <CardHeader>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <CardTitle>SofaScore Veri Merkezi</CardTitle>
              <div className="flex items-center gap-2">
                {data.sofascore?.event?.tournament_name ? (
                  <Badge variant="neutral" size="sm">{String(data.sofascore.event.tournament_name)}</Badge>
                ) : null}
                {data.sofascore?.event?.season_name ? (
                  <Badge variant="neutral" size="sm">{String(data.sofascore.event.season_name)}</Badge>
                ) : null}
              </div>
            </div>
            <CardDescription>Sezon istatistikleri, ilk 5 oyuncu ve lig sirasi</CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            {hasSeasonStats ? (
              <div className="rounded-xl border border-white/[0.08] bg-white/[0.02] p-4">
                <div className="grid grid-cols-[1fr_auto_1fr] gap-2 border-b border-white/[0.08] pb-3 text-xs font-semibold uppercase tracking-wide text-foreground-muted">
                  <span>{data.match.home_team.name}</span>
                  <span className="px-2 text-center">Sezon Istatistikleri</span>
                  <span className="text-right">{data.match.away_team.name}</span>
                </div>
                <div className="mt-3 space-y-2">
                  {seasonComparisonRows.map((row) => (
                    <div key={row.key} className="grid grid-cols-[1fr_auto_1fr] items-center gap-2 text-sm">
                      <span className="font-semibold text-foreground-primary">
                        {formatMetric(toNumber(row.home, 0), row.digits)}
                        {row.suffix}
                      </span>
                      <span className="rounded-md bg-white/[0.04] px-2 py-1 text-xs text-foreground-muted">{row.label}</span>
                      <span className="text-right font-semibold text-foreground-primary">
                        {formatMetric(toNumber(row.away, 0), row.digits)}
                        {row.suffix}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}

            <div className="grid gap-4 lg:grid-cols-2">
              {hasTopPlayers ? (
                <div className="rounded-xl border border-white/[0.08] bg-white/[0.02] p-4">
                  <p className="mb-3 text-sm font-semibold text-foreground-secondary">En iyi oyuncular</p>
                  <div className="grid gap-4 md:grid-cols-2">
                    <div>
                      <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-foreground-muted">
                        {data.match.home_team.name}
                      </p>
                      <ul className="space-y-2">
                        {homeTopPlayers.slice(0, 5).map((item, index) => {
                          const name = String(item.name ?? "Oyuncu");
                          const rating = toNumber(item.rating, 0);
                          const minutes = toNumber(item.minutes_played, 0);
                          return (
                            <li key={`home-top-${index}-${name}`} className="flex items-center justify-between rounded-lg border border-white/[0.06] px-3 py-2">
                              <div>
                                <p className="text-sm text-foreground-secondary">{name}</p>
                                <p className="text-xs text-foreground-muted">{minutes} dk</p>
                              </div>
                              <Badge variant="accent" size="sm">{formatMetric(rating, 2)}</Badge>
                            </li>
                          );
                        })}
                      </ul>
                    </div>
                    <div>
                      <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-foreground-muted">
                        {data.match.away_team.name}
                      </p>
                      <ul className="space-y-2">
                        {awayTopPlayers.slice(0, 5).map((item, index) => {
                          const name = String(item.name ?? "Oyuncu");
                          const rating = toNumber(item.rating, 0);
                          const minutes = toNumber(item.minutes_played, 0);
                          return (
                            <li key={`away-top-${index}-${name}`} className="flex items-center justify-between rounded-lg border border-white/[0.06] px-3 py-2">
                              <div>
                                <p className="text-sm text-foreground-secondary">{name}</p>
                                <p className="text-xs text-foreground-muted">{minutes} dk</p>
                              </div>
                              <Badge variant="accent" size="sm">{formatMetric(rating, 2)}</Badge>
                            </li>
                          );
                        })}
                      </ul>
                    </div>
                  </div>
                </div>
              ) : null}

              {hasStandings ? (
                <div className="rounded-xl border border-white/[0.08] bg-white/[0.02] p-4">
                  <p className="mb-3 text-sm font-semibold text-foreground-secondary">Lig sirasi</p>
                  <div className="space-y-3">
                    {[homeStanding, awayStanding].filter(Boolean).map((row, index) => {
                      const standing = row as Record<string, unknown>;
                      const teamName = String(standing.team_name ?? "Takim");
                      const position = toNumber(standing.position, 0);
                      const points = toNumber(standing.points, 0);
                      const played = toNumber(standing.played, 0);
                      const goalsFor = toNumber(standing.goals_for, 0);
                      const goalsAgainst = toNumber(standing.goals_against, 0);
                      return (
                        <div key={`standing-${index}-${teamName}`} className="rounded-lg border border-white/[0.06] px-3 py-3">
                          <div className="mb-1 flex items-center justify-between">
                            <p className="text-sm font-semibold text-foreground-secondary">{teamName}</p>
                            <Badge variant="neutral" size="sm">#{position}</Badge>
                          </div>
                          <p className="text-xs text-foreground-muted">
                            Puan: {points} | Oynanan: {played} | Gol: {goalsFor}:{goalsAgainst}
                          </p>
                        </div>
                      );
                    })}
                  </div>
                </div>
              ) : null}
            </div>
          </CardContent>
        </Card>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-[1fr_1.4fr]">
        {/* Left Column */}
        <div className="space-y-6">
          {/* Confidence Score */}
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle>Güven Skoru</CardTitle>
                <span className="text-2xl font-bold text-foreground-primary">
                  {toPercent(toNumber(data.analysis?.confidence_score, 0), 0)}
                </span>
              </div>
            </CardHeader>
            <CardContent>
              <Progress 
                value={toNumber(data.analysis?.confidence_score, 0)}
                variant={toNumber(data.analysis?.confidence_score, 0) >= 70 ? "success" : toNumber(data.analysis?.confidence_score, 0) >= 50 ? "warning" : "error"}
                size="lg"
                showValue
              />
            </CardContent>
          </Card>

          {/* Recent Form */}
          <Card>
            <CardHeader>
              <CardTitle>Son 6 Maç Formu</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <p className="text-xs text-foreground-muted mb-2">Ev Sahibi</p>
                <div className="flex gap-2">
                  {homeFormItems.map((item, index) => (
                    <FormBadge key={`home-${index}`} result={item.result} />
                  ))}
                </div>
              </div>
              <div>
                <p className="text-xs text-foreground-muted mb-2">Deplasman</p>
                <div className="flex gap-2">
                  {awayFormItems.map((item, index) => (
                    <FormBadge key={`away-${index}`} result={item.result} />
                  ))}
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Injuries */}
          <Card>
            <CardHeader>
              <CardTitle>Kadro Durumu</CardTitle>
              <CardDescription>Sakat ve cezalı oyuncular</CardDescription>
            </CardHeader>
            <CardContent>
              {injuriesFlat.length ? (
                <ul className="space-y-2">
                  {injuriesFlat.slice(0, 8).map((injury, index) => (
                    <li
                      key={`${injury.player}-${index}`}
                      className="flex items-center gap-3 p-3 rounded-xl bg-white/[0.02] border border-white/[0.04]"
                    >
                      <span className="w-2 h-2 rounded-full bg-warning" />
                      <div>
                        <p className="text-sm font-medium text-foreground-secondary">{injury.player}</p>
                        <p className="text-xs text-foreground-muted">
                          {injury.reason || injury.type || "Bilgi yok"}
                        </p>
                      </div>
                    </li>
                  ))}
                </ul>
              ) : (
                <div className="flex items-center gap-3 p-4 rounded-xl bg-success/10 border border-success/20">
                  <span className="w-2 h-2 rounded-full bg-success" />
                  <p className="text-sm text-success">Sakat/cezalı verisi bulunamadı</p>
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Right Column */}
        <div className="space-y-6">
          {/* Radar Chart */}
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle>10 Kriter Radar Grafiği</CardTitle>
                <Badge 
                  variant={data.analysis.recommended ? "success" : "warning"}
                  size="sm"
                >
                  {data.analysis.recommended ? "Önerilebilir" : "Sınırda"}
                </Badge>
              </div>
            </CardHeader>
            <CardContent>
              <RadarChart scores={criteriaScores} />
            </CardContent>
          </Card>

          {/* Markets Table */}
          <Card>
            <CardHeader>
              <CardTitle>Market Analizi</CardTitle>
              <CardDescription>Tüm marketlerin EV değerleri</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-white/[0.06]">
                      <th className="text-left py-3 px-2 text-xs font-semibold uppercase text-foreground-muted">Market</th>
                      <th className="text-left py-3 px-2 text-xs font-semibold uppercase text-foreground-muted">Olasılık</th>
                      <th className="text-left py-3 px-2 text-xs font-semibold uppercase text-foreground-muted">Oran</th>
                      <th className="text-left py-3 px-2 text-xs font-semibold uppercase text-foreground-muted">EV</th>
                      <th className="text-center py-3 px-2 text-xs font-semibold uppercase text-foreground-muted">Öneri</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/[0.04]">
                    {allMarkets.slice(0, 16).map((market, index) => (
                      <tr 
                        key={`${market.market_type ?? market.market ?? "market"}-${market.predicted_outcome ?? index}`}
                        className={cn(
                          "hover:bg-white/[0.02] transition-colors",
                          market.recommended && "bg-success/5"
                        )}
                      >
                        <td className="py-3 px-2 text-foreground-secondary">{market.market_type ?? market.market ?? "-"}</td>
                        <td className="py-3 px-2 text-foreground-muted">%{(toNumber(market.probability, 0) * 100).toFixed(1)}</td>
                        <td className="py-3 px-2 font-medium text-foreground-primary">{toNumber(market.odd, 0).toFixed(2)}</td>
                        <td className={cn(
                          "py-3 px-2 font-medium",
                          toNumber(market.ev_percentage, 0) >= 0 ? "text-success" : "text-error"
                        )}>
                          {toNumber(market.ev_percentage, 0) >= 0 ? "+" : ""}{toNumber(market.ev_percentage, 0).toFixed(1)}%
                        </td>
                        <td className="py-3 px-2 text-center">
                          {market.recommended ? (
                            <Badge variant="success" size="sm">✓</Badge>
                          ) : (
                            <span className="text-foreground-muted">-</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>

      {/* H2H & xG */}
      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>H2H Son 5 Maç</CardTitle>
            <CardDescription>
              Oran: %{(toNumber(data.h2h?.summary?.ratio, 0.5) * 100).toFixed(1)} | 
              Ev: {toNumber(data.h2h?.summary?.home_wins, 0)} | 
              Beraberlik: {toNumber(data.h2h?.summary?.draws, 0)} | 
              Deplasman: {toNumber(data.h2h?.summary?.away_wins, 0)}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {h2hMatches.map((item, index) => {
                const raw = item as Record<string, unknown>;
                const teams = (raw.teams as Record<string, unknown>) ?? {};
                const goals = (raw.goals as Record<string, unknown>) ?? {};
                const homeName =
                  (raw.home_team as string | undefined) ??
                  ((teams.home as Record<string, unknown>)?.name as string | undefined) ??
                  "Ev";
                const awayName =
                  (raw.away_team as string | undefined) ??
                  ((teams.away as Record<string, unknown>)?.name as string | undefined) ??
                  "Dep";
                const homeGoals = Number(
                  (raw.home_goals as number | string | undefined) ??
                    (goals.home as number | string | undefined) ??
                    0
                );
                const awayGoals = Number(
                  (raw.away_goals as number | string | undefined) ??
                    (goals.away as number | string | undefined) ??
                    0
                );
                return (
                  <div
                    key={index}
                    className="flex items-center justify-between p-3 rounded-xl bg-white/[0.02] border border-white/[0.04]"
                  >
                    <span className="text-sm text-foreground-secondary">{homeName} vs {awayName}</span>
                    <Badge variant="neutral" size="sm">{homeGoals} - {awayGoals}</Badge>
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>xG Karşılaştırma</CardTitle>
            <CardDescription>Beklenen Gol (Expected Goals)</CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            <div>
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-medium text-foreground-secondary">{data.match.home_team.name}</span>
                <span className="text-lg font-bold text-foreground-primary">{homeAttackXg.toFixed(2)}</span>
              </div>
              <Progress 
                value={Math.min(100, homeAttackXg * 30)} 
                variant="default"
                size="lg"
              />
              <p className="mt-2 text-xs text-foreground-muted">Defans xG: {homeDefenseXg.toFixed(2)}</p>
            </div>
            <div>
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-medium text-foreground-secondary">{data.match.away_team.name}</span>
                <span className="text-lg font-bold text-foreground-primary">{awayAttackXg.toFixed(2)}</span>
              </div>
              <Progress 
                value={Math.min(100, awayAttackXg * 30)} 
                variant="warning"
                size="lg"
              />
              <p className="mt-2 text-xs text-foreground-muted">Defans xG: {awayDefenseXg.toFixed(2)}</p>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Action */}
      <div className="flex flex-wrap items-center gap-4">
        <Button 
          size="lg" 
          onClick={handleAddCoupon}
          className={cn(
            saved && "bg-success hover:bg-success/90"
          )}
        >
          {saved ? (
            <>
              <svg className="w-5 h-5 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
              Kupona Eklendi
            </>
          ) : (
            <>
              <svg className="w-5 h-5 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
              Kupona Ekle
            </>
          )}
        </Button>
        
        {saved && (
          <p className="text-sm text-success animate-fade-in">
            Maç başarıyla kuponunuza eklendi.
          </p>
        )}
      </div>
    </section>
  );
}
