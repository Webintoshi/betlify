"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { addCouponSelection } from "@/lib/coupon-store";
import { getMatchAnalysis, type MatchAnalysisResponse } from "@/lib/api";
import { formatDateTime, initials, toPercent } from "@/lib/utils";

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
          return <polygon key={stepIndex} points={points} fill="none" stroke="#2f3047" strokeWidth="1" />;
        })}

        {labels.map((label, index) => {
          const angle = -Math.PI / 2 + index * angleStep;
          const x = center + Math.cos(angle) * radius;
          const y = center + Math.sin(angle) * radius;
          const tx = center + Math.cos(angle) * (radius + 18);
          const ty = center + Math.sin(angle) * (radius + 18);
          return (
            <g key={label}>
              <line x1={center} y1={center} x2={x} y2={y} stroke="#2f3047" strokeWidth="1" />
              <text x={tx} y={ty} textAnchor="middle" className="fill-zinc-400 text-[9px]">
                {label}
              </text>
            </g>
          );
        })}

        <polygon points={polygonPoints} fill="rgba(99,102,241,0.35)" stroke="#6366f1" strokeWidth="2" />
      </svg>
    </div>
  );
}

function formColor(result: "W" | "D" | "L"): string {
  if (result === "W") {
    return "bg-emerald-500/30 text-emerald-300";
  }
  if (result === "D") {
    return "bg-amber-500/30 text-amber-300";
  }
  return "bg-rose-500/30 text-rose-300";
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

  return (
    <section className="space-y-6">
      <div>
        <p className="text-xs uppercase tracking-[0.2em] text-zinc-500">Maç Detay</p>
        <h1 className="mt-1 text-3xl font-bold text-white">Analiz Ekranı</h1>
      </div>

      {loading ? <p className="text-sm text-zinc-400">Maç analizi yükleniyor...</p> : null}
      {error ? <p className="rounded-xl bg-red-900/20 p-3 text-sm text-red-300">{error}</p> : null}

      {data?.match ? (
        <>
          <div className="grid gap-4 lg:grid-cols-[1fr_1.3fr]">
            <Card className="space-y-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="flex h-12 w-12 items-center justify-center rounded-full bg-[#26263a] text-lg font-semibold text-white">
                    {initials(data.match.home_team.name)}
                  </div>
                  <p className="text-lg font-semibold text-white">{data.match.home_team.name}</p>
                </div>
                <span className="text-zinc-500">vs</span>
                <div className="flex items-center gap-2">
                  <p className="text-lg font-semibold text-white">{data.match.away_team.name}</p>
                  <div className="flex h-12 w-12 items-center justify-center rounded-full bg-[#26263a] text-lg font-semibold text-white">
                    {initials(data.match.away_team.name)}
                  </div>
                </div>
              </div>

              <div className="rounded-xl bg-[#141420] p-3 text-sm text-zinc-300">
                <p>{data.match.league}</p>
                <p className="mt-1 text-zinc-400">{formatDateTime(data.match.match_date)}</p>
              </div>

              <div className="space-y-2">
                <CardTitle>Son 6 Maç Formu</CardTitle>
                <div className="space-y-2">
                  <div className="flex flex-wrap gap-2">
                    {(data.form?.home ?? []).map((item, index) => (
                      <span key={`home-${index}`} className={`rounded-md px-2 py-1 text-xs font-medium ${formColor(item.result)}`}>
                        {item.result}
                      </span>
                    ))}
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {(data.form?.away ?? []).map((item, index) => (
                      <span key={`away-${index}`} className={`rounded-md px-2 py-1 text-xs font-medium ${formColor(item.result)}`}>
                        {item.result}
                      </span>
                    ))}
                  </div>
                </div>
              </div>

              <div className="space-y-2">
                <CardTitle>Kadro Durumu</CardTitle>
                {(data.injuries ?? []).length ? (
                  <ul className="space-y-2 text-sm text-zinc-300">
                    {(data.injuries ?? []).slice(0, 8).map((injury, index) => (
                      <li key={`${injury.player}-${index}`} className="rounded-lg bg-[#141420] p-2">
                        {injury.player} - {injury.reason || injury.type || "Bilgi yok"}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-sm text-zinc-500">Sakat/cezalı verisi bulunamadı.</p>
                )}
              </div>

              <div className="rounded-xl border border-white/5 bg-[#141420] p-3">
                <div className="mb-2 flex items-center justify-between text-xs text-zinc-400">
                  <span>Güven Skoru</span>
                  <span>{toPercent(data.analysis.confidence_score, 0)}</span>
                </div>
                <Progress value={data.analysis.confidence_score} />
              </div>
            </Card>

            <Card className="space-y-4">
              <div className="flex items-center justify-between">
                <CardTitle>10 Kriter Radar Grafiği</CardTitle>
                <Badge variant={data.analysis.recommended ? "success" : "warning"}>
                  {data.analysis.recommended ? "Önerilebilir" : "Sınırda"}
                </Badge>
              </div>
              <RadarChart scores={criteriaScores} />

              <div className="overflow-x-auto">
                <table className="w-full min-w-[560px] text-sm">
                  <thead className="text-left text-xs uppercase tracking-wide text-zinc-500">
                    <tr>
                      <th className="pb-2">Market</th>
                      <th className="pb-2">Olasılık</th>
                      <th className="pb-2">Oran</th>
                      <th className="pb-2">EV</th>
                      <th className="pb-2">Öneri</th>
                    </tr>
                  </thead>
                  <tbody>
                    {allMarkets.slice(0, 16).map((market) => (
                      <tr key={`${market.market_type}-${market.predicted_outcome}`} className="border-t border-white/5 text-zinc-300">
                        <td className="py-2">{market.market_type}</td>
                        <td className="py-2">%{(market.probability * 100).toFixed(1)}</td>
                        <td className="py-2">{market.odd.toFixed(2)}</td>
                        <td className={`py-2 ${market.ev_percentage >= 0 ? "text-emerald-300" : "text-rose-300"}`}>
                          {market.ev_percentage >= 0 ? "+" : ""}
                          {market.ev_percentage.toFixed(1)}%
                        </td>
                        <td className="py-2">{market.recommended ? "✅" : "❌"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <Card className="space-y-3">
              <CardTitle>H2H Son 5 Maç</CardTitle>
              <div className="text-xs text-zinc-400">
                Oran: %{((data.h2h?.summary.ratio ?? 0.5) * 100).toFixed(1)} | Ev galibiyeti: {data.h2h?.summary.home_wins ?? 0} |
                Beraberlik: {data.h2h?.summary.draws ?? 0} | Deplasman: {data.h2h?.summary.away_wins ?? 0}
              </div>
              <table className="w-full text-sm">
                <thead className="text-left text-xs uppercase tracking-wide text-zinc-500">
                  <tr>
                    <th className="pb-2">Maç</th>
                    <th className="pb-2">Skor</th>
                  </tr>
                </thead>
                <tbody>
                  {(data.h2h?.last5 ?? []).map((item, index) => {
                    const raw = item as Record<string, unknown>;
                    const teams = (raw.teams as Record<string, unknown>) ?? {};
                    const goals = (raw.goals as Record<string, unknown>) ?? {};
                    const homeName = ((teams.home as Record<string, unknown>)?.name as string) ?? "Ev";
                    const awayName = ((teams.away as Record<string, unknown>)?.name as string) ?? "Dep";
                    const homeGoals = Number((goals.home as number | string | undefined) ?? 0);
                    const awayGoals = Number((goals.away as number | string | undefined) ?? 0);
                    return (
                      <tr key={index} className="border-t border-white/5 text-zinc-300">
                        <td className="py-2">
                          {homeName} vs {awayName}
                        </td>
                        <td className="py-2">
                          {homeGoals} - {awayGoals}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </Card>

            <Card className="space-y-3">
              <CardTitle>xG Karşılaştırma</CardTitle>
              <div className="space-y-3">
                <div>
                  <div className="mb-1 flex justify-between text-xs text-zinc-400">
                    <span>{data.match.home_team.name}</span>
                    <span>{(data.xg?.home ?? 0).toFixed(2)}</span>
                  </div>
                  <Progress value={Math.min(100, (data.xg?.home ?? 0) * 30)} />
                </div>
                <div>
                  <div className="mb-1 flex justify-between text-xs text-zinc-400">
                    <span>{data.match.away_team.name}</span>
                    <span>{(data.xg?.away ?? 0).toFixed(2)}</span>
                  </div>
                  <Progress value={Math.min(100, (data.xg?.away ?? 0) * 30)} barClassName="bg-amber-400" />
                </div>
              </div>
            </Card>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <Button onClick={handleAddCoupon}>Kupona Ekle</Button>
            {saved ? <p className="text-sm text-emerald-300">Kupona eklendi.</p> : null}
          </div>
        </>
      ) : null}
    </section>
  );
}
