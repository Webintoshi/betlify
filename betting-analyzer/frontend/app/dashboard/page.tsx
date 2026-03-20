"use client";

import { useEffect, useMemo, useState } from "react";
import MatchCard from "@/components/MatchCard";
import { Card, CardDescription, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { getHistory, getTodayMatches, type DashboardMatch } from "@/lib/api";
import { addCouponSelection, getCouponSelections } from "@/lib/coupon-store";
import { cn, toPercent } from "@/lib/utils";

function SummaryCard({
  title,
  value,
  subtitle,
  icon,
  trend,
  trendUp
}: {
  title: string;
  value: string;
  subtitle: string;
  icon: React.ReactNode;
  trend?: string;
  trendUp?: boolean;
}) {
  return (
    <Card hover className="relative">
      <div className="flex items-start justify-between">
        <div>
          <CardDescription className="flex items-center gap-2 mb-2">
            <span className="text-accent">{icon}</span>
            <span className="uppercase tracking-wider">{title}</span>
          </CardDescription>
          <div className="text-3xl font-black text-foreground-primary tracking-tight">
            {value}
          </div>
        </div>
        {trend && (
          <Badge 
            variant={trendUp ? "success" : "neutral"} 
            size="sm"
          >
            {trend}
          </Badge>
        )}
      </div>
      <p className="mt-3 text-xs font-bold text-foreground-muted uppercase tracking-wide">{subtitle}</p>
    </Card>
  );
}

export default function DashboardPage() {
  const [matches, setMatches] = useState<DashboardMatch[]>([]);
  const [selectedLeague, setSelectedLeague] = useState<string>("all");
  const [minConfidence, setMinConfidence] = useState<number>(51);
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
        const [matchesResponse, historyResponse] = await Promise.all([
          getTodayMatches(50),
          getHistory()
        ]);
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
    () => [
      "all",
      ...Array.from(new Set(matches.map((match) => match.league))).sort((a, b) =>
        a.localeCompare(b)
      )
    ],
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

  const recommendedCount = useMemo(
    () => filteredMatches.filter((match) => match.confidence_score > 60).length,
    [filteredMatches]
  );

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
    <section className="space-y-8 animate-fade-in">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4 pb-6 border-b-2 border-card-border">
        <div>
          <div className="flex items-center gap-3 mb-2">
            <Badge variant="accent" size="sm">V2.0</Badge>
            <p className="text-xs font-black uppercase tracking-[0.3em] text-accent">
              Betlify
            </p>
          </div>
          <h1 className="text-display-sm text-foreground-primary uppercase tracking-tight">
            Dashboard
          </h1>
          <p className="mt-1 text-sm font-bold text-foreground-muted uppercase tracking-wide">
            Günlük maç analizleri ve istatistikler
          </p>
        </div>
        <div className="flex items-center gap-2 text-xs font-bold text-success uppercase tracking-wide">
          <span className="w-2.5 h-2.5 rounded-full bg-success animate-pulse" />
          Canlı veri akışı aktif
        </div>
      </div>

      {/* Summary Cards */}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <SummaryCard
          title="Bugünkü Maçlar"
          value={String(filteredMatches.length)}
          subtitle="Filtrelenmiş liste"
          icon={
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
            </svg>
          }
        />
        <SummaryCard
          title="Önerilen Bahis"
          value={String(recommendedCount)}
          subtitle="Güven skoru > 60"
          icon={
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          }
          trend="+12%"
          trendUp
        />
        <SummaryCard
          title="Haftalık İsabet"
          value={toPercent(weeklyAccuracy, 1)}
          subtitle="Son 7 gün performansı"
          icon={
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
            </svg>
          }
        />
        <SummaryCard
          title="Toplam Kupon"
          value={String(totalCoupons)}
          subtitle="Sistemde kayıtlı"
          icon={
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 5v2m0 4v2m0 4v2M5 5a2 2 0 00-2 2v3a2 2 0 110 4v3a2 2 0 002 2h14a2 2 0 002-2v-3a2 2 0 110-4V7a2 2 0 00-2-2H5z" />
            </svg>
          }
        />
      </div>

      {/* Filters */}
      <Card>
        <div className="flex items-center gap-3 mb-5 pb-4 border-b-2 border-card-border">
          <div className="w-10 h-10 rounded-lg bg-accent flex items-center justify-center">
            <svg className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2.586a1 1 0 01-.293.707l-6.414 6.414a1 1 0 00-.293.707V17l-4 4v-6.586a1 1 0 00-.293-.707L3.293 7.293A1 1 0 013 6.586V4z" />
            </svg>
          </div>
          <CardTitle>Filtreler</CardTitle>
        </div>
        
        <div className="grid gap-5 md:grid-cols-2">
          {/* League Filter */}
          <div className="space-y-2">
            <label className="text-xs font-black uppercase tracking-wide text-foreground-tertiary">
              Lig Seçimi
            </label>
            <select
              value={selectedLeague}
              onChange={(event) => setSelectedLeague(event.target.value)}
              className={cn(
                "w-full rounded-lg border-2 border-card-border bg-background-secondary",
                "px-4 py-3 text-sm font-bold text-foreground-primary uppercase tracking-wide",
                "focus:outline-none focus:border-accent",
                "transition-colors duration-150"
              )}
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
          </div>

          {/* Confidence Filter */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <label className="text-xs font-black uppercase tracking-wide text-foreground-tertiary">
                Minimum Güven Skoru
              </label>
              <Badge variant="accent" size="sm">{minConfidence}%</Badge>
            </div>
            <input
              type="range"
              min={40}
              max={90}
              step={1}
              value={minConfidence}
              onChange={(event) => setMinConfidence(Number(event.target.value))}
              className="w-full"
            />
            <div className="flex justify-between text-[10px] font-bold text-foreground-muted uppercase">
              <span>40%</span>
              <span>90%</span>
            </div>
          </div>
        </div>
      </Card>

      {/* Loading State */}
      {loading && (
        <div className="flex items-center justify-center py-16">
          <div className="flex items-center gap-3">
            <svg className="animate-spin h-6 w-6 text-accent" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
            </svg>
            <span className="text-sm font-black text-accent uppercase tracking-wide">Maçlar yükleniyor...</span>
          </div>
        </div>
      )}

      {/* Error State */}
      {error && (
        <div className="rounded-xl bg-error/10 border-2 border-error p-5 flex items-start gap-4">
          <div className="w-10 h-10 rounded-lg bg-error/20 flex items-center justify-center flex-shrink-0">
            <svg className="w-5 h-5 text-error-bright" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
          <div>
            <p className="text-sm font-black text-error-bright uppercase tracking-wide">Bir hata oluştu</p>
            <p className="text-xs font-bold text-error/70 mt-1">{error}</p>
          </div>
        </div>
      )}

      {/* Matches Grid */}
      {!loading && !error && (
        <>
          <div className="flex items-center justify-between pb-4 border-b-2 border-card-border">
            <div className="flex items-center gap-3">
              <h2 className="text-lg font-black text-foreground-primary uppercase tracking-wide">
                Maç Listesi
              </h2>
              <Badge variant="neutral" size="md">
                {filteredMatches.length}
              </Badge>
            </div>
          </div>

          <div className="grid gap-5 xl:grid-cols-2">
            {filteredMatches.map((match, index) => (
              <div 
                key={match.match_id}
                style={{ animationDelay: `${index * 50}ms` }}
                className="animate-fade-in"
              >
                <MatchCard
                  match={match}
                  isSelected={selectedMatches.has(match.match_id)}
                  onAdd={handleAddCoupon}
                />
              </div>
            ))}
          </div>

          {!filteredMatches.length && (
            <Card className="text-center py-16">
              <div className="flex flex-col items-center gap-5">
                <div className="w-16 h-16 rounded-lg bg-card-hover flex items-center justify-center">
                  <svg className="w-8 h-8 text-foreground-muted" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.172 16.172a4 4 0 015.656 0M9 10h.01M15 10h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                </div>
                <div>
                  <p className="text-sm font-black text-foreground-secondary uppercase tracking-wide">
                    Filtrelere uygun maç bulunamadı
                  </p>
                  <p className="text-xs font-bold text-foreground-muted mt-1 uppercase">
                    Farklı filtreler deneyin
                  </p>
                </div>
              </div>
            </Card>
          )}
        </>
      )}
    </section>
  );
}
