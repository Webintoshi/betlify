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

function TeamAvatar({ name }: { name: string }) {
  return (
    <div className="flex flex-col items-center gap-3">
      <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-accent/20 to-accent-secondary/10 border border-accent/20 flex items-center justify-center">
        <span className="text-lg font-bold text-foreground-primary">
          {initials(name)}
        </span>
      </div>
      <span className="text-sm font-semibold text-foreground-primary text-center max-w-[120px]">
        {name}
      </span>
    </div>
  );
}

export default function MatchDetailsPage() {
  const params = useParams<{ id: string }>();
  const matchId = params.id;
  const [data, setData] = useState<MatchAnalysisResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string>("");
  const [saved, setSaved] = useState<boolean>(false);

  useEffect(() => {
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

  const criteriaScores = useMemo(() => data?.analysis.criteria_scores ?? {}, [data]);
  const allMarkets = data?.ev.all_markets ?? [];

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

  if (loading) {
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
              <TeamAvatar name={data.match.home_team.name} />
              
              <div className="flex flex-col items-center gap-2">
                <span className="text-3xl font-bold text-foreground-muted">VS</span>
                {data.analysis.recommended ? (
                  <Badge variant="success" size="sm" dot>Önerilir</Badge>
                ) : (
                  <Badge variant="warning" size="sm" dot>Sınırda</Badge>
                )}
              </div>
              
              <TeamAvatar name={data.match.away_team.name} />
            </div>
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-6 lg:grid-cols-[1fr_1.4fr]">
        {/* Left Column */}
        <div className="space-y-6">
          {/* Confidence Score */}
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle>Güven Skoru</CardTitle>
                <span className="text-2xl font-bold text-foreground-primary">
                  {toPercent(data.analysis.confidence_score, 0)}
                </span>
              </div>
            </CardHeader>
            <CardContent>
              <Progress 
                value={data.analysis.confidence_score}
                variant={data.analysis.confidence_score >= 70 ? "success" : data.analysis.confidence_score >= 50 ? "warning" : "error"}
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
                  {(data.form?.home ?? []).map((item, index) => (
                    <FormBadge key={`home-${index}`} result={item.result} />
                  ))}
                </div>
              </div>
              <div>
                <p className="text-xs text-foreground-muted mb-2">Deplasman</p>
                <div className="flex gap-2">
                  {(data.form?.away ?? []).map((item, index) => (
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
              {(data.injuries ?? []).length ? (
                <ul className="space-y-2">
                  {(data.injuries ?? []).slice(0, 8).map((injury, index) => (
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
                    {allMarkets.slice(0, 16).map((market) => (
                      <tr 
                        key={`${market.market_type}-${market.predicted_outcome}`}
                        className={cn(
                          "hover:bg-white/[0.02] transition-colors",
                          market.recommended && "bg-success/5"
                        )}
                      >
                        <td className="py-3 px-2 text-foreground-secondary">{market.market_type}</td>
                        <td className="py-3 px-2 text-foreground-muted">%{(market.probability * 100).toFixed(1)}</td>
                        <td className="py-3 px-2 font-medium text-foreground-primary">{market.odd.toFixed(2)}</td>
                        <td className={cn(
                          "py-3 px-2 font-medium",
                          market.ev_percentage >= 0 ? "text-success" : "text-error"
                        )}>
                          {market.ev_percentage >= 0 ? "+" : ""}{market.ev_percentage.toFixed(1)}%
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
              Oran: %{((data.h2h?.summary.ratio ?? 0.5) * 100).toFixed(1)} | 
              Ev: {data.h2h?.summary.home_wins ?? 0} | 
              Beraberlik: {data.h2h?.summary.draws ?? 0} | 
              Deplasman: {data.h2h?.summary.away_wins ?? 0}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {(data.h2h?.last5 ?? []).map((item, index) => {
                const raw = item as Record<string, unknown>;
                const teams = (raw.teams as Record<string, unknown>) ?? {};
                const goals = (raw.goals as Record<string, unknown>) ?? {};
                const homeName = ((teams.home as Record<string, unknown>)?.name as string) ?? "Ev";
                const awayName = ((teams.away as Record<string, unknown>)?.name as string) ?? "Dep";
                const homeGoals = Number((goals.home as number | string | undefined) ?? 0);
                const awayGoals = Number((goals.away as number | string | undefined) ?? 0);
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
                <span className="text-lg font-bold text-foreground-primary">{(data.xg?.home ?? 0).toFixed(2)}</span>
              </div>
              <Progress 
                value={Math.min(100, (data.xg?.home ?? 0) * 30)} 
                variant="default"
                size="lg"
              />
            </div>
            <div>
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-medium text-foreground-secondary">{data.match.away_team.name}</span>
                <span className="text-lg font-bold text-foreground-primary">{(data.xg?.away ?? 0).toFixed(2)}</span>
              </div>
              <Progress 
                value={Math.min(100, (data.xg?.away ?? 0) * 30)} 
                variant="warning"
                size="lg"
              />
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
