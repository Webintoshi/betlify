"use client";

import { useEffect, useMemo, useState } from "react";
import MatchCard from "@/components/MatchCard";
import { Card, CardDescription, CardTitle } from "@/components/ui/card";
import { getHistory, getTodayMatches, type DashboardMatch } from "@/lib/api";
import { addCouponSelection, getCouponSelections } from "@/lib/coupon-store";
import { toPercent } from "@/lib/utils";

function SummaryCard({
  title,
  value,
  subtitle
}: {
  title: string;
  value: string;
  subtitle: string;
}) {
  return (
    <Card className="space-y-1">
      <CardDescription>{title}</CardDescription>
      <CardTitle className="text-2xl font-bold text-white">{value}</CardTitle>
      <p className="text-xs text-zinc-500">{subtitle}</p>
    </Card>
  );
}

export default function DashboardPage() {
  const [matches, setMatches] = useState<DashboardMatch[]>([]);
  const [selectedLeague, setSelectedLeague] = useState<string>("all");
  const [minConfidence, setMinConfidence] = useState<number>(60);
  const [selectedMatches, setSelectedMatches] = useState<Set<string>>(new Set());
  const [weeklyAccuracy, setWeeklyAccuracy] = useState<number>(0);
  const [totalCoupons, setTotalCoupons] = useState<number>(0);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string>("");

  useEffect(() => {
    setSelectedMatches(new Set(getCouponSelections().map((item) => item.match_id)));
    const load = async () => {
      setLoading(true);
      setError("");
      try {
        const [matchesResponse, historyResponse] = await Promise.all([getTodayMatches(50), getHistory()]);
        setMatches(matchesResponse.matches ?? []);
        setWeeklyAccuracy(historyResponse.summary.weekly_accuracy_percentage ?? 0);
        setTotalCoupons(historyResponse.summary.total_coupons ?? 0);
      } catch (requestError) {
        setError(requestError instanceof Error ? requestError.message : "Veriler alınamadı.");
      } finally {
        setLoading(false);
      }
    };
    void load();
  }, []);

  const leagues = useMemo(
    () => ["all", ...Array.from(new Set(matches.map((match) => match.league))).sort((a, b) => a.localeCompare(b))],
    [matches]
  );

  const filteredMatches = useMemo(
    () =>
      matches.filter((match) => {
        const leagueOk = selectedLeague === "all" || match.league === selectedLeague;
        const confidenceOk = match.confidence_score >= minConfidence;
        return leagueOk && confidenceOk;
      }),
    [matches, minConfidence, selectedLeague]
  );

  const recommendedCount = useMemo(() => filteredMatches.filter((match) => match.confidence_score > 60).length, [filteredMatches]);

  const handleAddCoupon = (match: DashboardMatch) => {
    addCouponSelection({
      match_id: match.match_id,
      home_team: match.home_team,
      away_team: match.away_team,
      market_type: match.market_type,
      odd: 1.8,
      confidence_score: match.confidence_score,
      ev_percentage: match.ev_percentage
    });
    setSelectedMatches(new Set(getCouponSelections().map((item) => item.match_id)));
  };

  return (
    <section className="space-y-6">
      <div>
        <p className="text-xs uppercase tracking-[0.2em] text-zinc-500">Betlify</p>
        <h1 className="mt-1 text-3xl font-bold text-white">Dashboard</h1>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <SummaryCard title="Bugünkü maç sayısı" value={String(filteredMatches.length)} subtitle="Filtrelenmiş liste" />
        <SummaryCard title="Önerilen bahis" value={String(recommendedCount)} subtitle="Güven > 60" />
        <SummaryCard title="Bu haftaki isabet" value={toPercent(weeklyAccuracy, 1)} subtitle="Son 7 gün sonuçları" />
        <SummaryCard title="Toplam kupon" value={String(totalCoupons)} subtitle="Sistemde kayıtlı kupon" />
      </div>

      <Card className="space-y-4">
        <div className="grid gap-4 md:grid-cols-2">
          <label className="text-sm text-zinc-300">
            Lig
            <select
              value={selectedLeague}
              onChange={(event) => setSelectedLeague(event.target.value)}
              className="mt-2 w-full rounded-xl border border-white/10 bg-[#141420] px-3 py-2 text-sm text-zinc-100"
            >
              <option value="all">Tüm Ligler</option>
              {leagues
                .filter((league) => league !== "all")
                .map((league) => (
                  <option key={league} value={league}>
                    {league}
                  </option>
                ))}
            </select>
          </label>

          <label className="text-sm text-zinc-300">
            Min güven skoru: <span className="font-semibold text-white">{minConfidence}</span>
            <input
              type="range"
              min={40}
              max={90}
              step={1}
              value={minConfidence}
              onChange={(event) => setMinConfidence(Number(event.target.value))}
              className="mt-3 w-full"
            />
          </label>
        </div>
      </Card>

      {loading ? <p className="text-sm text-zinc-400">Maçlar yükleniyor...</p> : null}
      {error ? <p className="rounded-xl bg-red-900/20 p-3 text-sm text-red-300">{error}</p> : null}

      <div className="grid gap-4 xl:grid-cols-2">
        {filteredMatches.map((match) => (
          <MatchCard
            key={match.match_id}
            match={match}
            isSelected={selectedMatches.has(match.match_id)}
            onAdd={handleAddCoupon}
          />
        ))}
      </div>

      {!loading && !filteredMatches.length ? (
        <Card>
          <p className="text-sm text-zinc-400">Filtrelere uygun maç bulunamadı.</p>
        </Card>
      ) : null}
    </section>
  );
}
