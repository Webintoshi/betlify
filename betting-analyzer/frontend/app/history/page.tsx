"use client";

import { useEffect, useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Card, CardDescription, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { getHistory, type HistoryItem, type HistoryResponse } from "@/lib/api";
import { cn, formatDateTime, toPercent } from "@/lib/utils";

type LocalSummary = {
  total: number;
  pending: number;
  resolved: number;
  correct: number;
  wrong: number;
  accuracy: number;
};

type MarketMetric = {
  key: string;
  label: string;
  total: number;
  resolved: number;
  correct: number;
  accuracy: number;
};

function buildSummary(items: HistoryItem[]): LocalSummary {
  const total = items.length;
  const pending = items.filter((item) => item.was_correct === null).length;
  const resolved = items.filter((item) => item.was_correct !== null);
  const correct = resolved.filter((item) => item.was_correct === true).length;
  const wrong = resolved.filter((item) => item.was_correct === false).length;
  const accuracy = resolved.length > 0 ? (correct / resolved.length) * 100 : 0;

  return {
    total,
    pending,
    resolved: resolved.length,
    correct,
    wrong,
    accuracy,
  };
}

function buildMarketMetric(key: string, label: string, items: HistoryItem[]): MarketMetric {
  const summary = buildSummary(items);
  return {
    key,
    label,
    total: summary.total,
    resolved: summary.resolved,
    correct: summary.correct,
    accuracy: summary.accuracy,
  };
}

function StatCard({
  title,
  value,
  icon,
  variant = "neutral",
}: {
  title: string;
  value: string;
  icon: React.ReactNode;
  variant?: "neutral" | "success" | "warning" | "error" | "accent";
}) {
  return (
    <Card hover>
      <div className="flex items-center justify-between">
        <div>
          <CardDescription>{title}</CardDescription>
          <p className="mt-1 text-2xl font-black text-foreground-primary">{value}</p>
        </div>
        <Badge variant={variant} size="sm">
          {title}
        </Badge>
      </div>
      <div className="mt-3 text-foreground-muted">{icon}</div>
    </Card>
  );
}

function ResultBadge({ correct }: { correct: boolean | null }) {
  if (correct === null) {
    return (
      <Badge variant="neutral" size="sm" dot>
        Bekliyor
      </Badge>
    );
  }

  if (correct) {
    return (
      <Badge variant="success" size="sm" dot>
        Dogru
      </Badge>
    );
  }

  return (
    <Badge variant="error" size="sm" dot>
      Yanlis
    </Badge>
  );
}

export default function HistoryPage() {
  const [history, setHistory] = useState<HistoryResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string>("");
  const [startDate, setStartDate] = useState<string>("");
  const [endDate, setEndDate] = useState<string>("");
  const [correct, setCorrect] = useState<string>("all");
  const [selectedMarket, setSelectedMarket] = useState<string>("all");

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      setError("");
      try {
        const response = await getHistory({
          startDate: startDate || undefined,
          endDate: endDate || undefined,
          correct,
        });
        setHistory(response);
      } catch (requestError) {
        setError(requestError instanceof Error ? requestError.message : "Gecmis verisi alinamadi.");
      } finally {
        setLoading(false);
      }
    };
    void load();
  }, [startDate, endDate, correct]);

  const allItems = useMemo<HistoryItem[]>(() => history?.items ?? [], [history?.items]);

  const marketMetrics = useMemo(() => {
    const grouped = new Map<string, HistoryItem[]>();
    for (const item of allItems) {
      const key = item.market_type || "Bilinmeyen";
      const list = grouped.get(key);
      if (list) {
        list.push(item);
      } else {
        grouped.set(key, [item]);
      }
    }

    const metrics = Array.from(grouped.entries())
      .map(([key, items]) => buildMarketMetric(key, key, items))
      .sort((a, b) => {
        if (b.resolved !== a.resolved) {
          return b.resolved - a.resolved;
        }
        return a.label.localeCompare(b.label, "tr");
      });

    return [buildMarketMetric("all", "Tumu", allItems), ...metrics];
  }, [allItems]);

  useEffect(() => {
    if (!marketMetrics.some((metric) => metric.key === selectedMarket)) {
      setSelectedMarket("all");
    }
  }, [marketMetrics, selectedMarket]);

  const selectedItems = useMemo(
    () =>
      selectedMarket === "all"
        ? allItems
        : allItems.filter((item) => item.market_type === selectedMarket),
    [allItems, selectedMarket]
  );

  const summary = useMemo(() => buildSummary(selectedItems), [selectedItems]);
  const resolvedItems = useMemo(
    () => selectedItems.filter((item) => item.was_correct !== null),
    [selectedItems]
  );

  const selectedMarketLabel = useMemo(() => {
    const metric = marketMetrics.find((item) => item.key === selectedMarket);
    return metric?.label ?? "Tumu";
  }, [marketMetrics, selectedMarket]);

  return (
    <section className="space-y-8 animate-fade-in">
      <div>
        <div className="mb-2 flex items-center gap-3">
          <Badge variant="accent" size="sm">
            Gecmis
          </Badge>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-foreground-muted">Betlify</p>
        </div>
        <h1 className="text-display-sm text-foreground-primary">Tahmin Sonuclari</h1>
        <p className="mt-1 text-sm text-foreground-tertiary">
          Bekleyen ve sonuclanan tahminleri ayri takip ederek daha dogru performans gorunumu.
        </p>
      </div>

      {!loading && !error && (
        <>
          <div className="grid gap-4 sm:grid-cols-3">
            <StatCard
              title="Toplam Tahmin"
              value={String(summary.total)}
              variant="accent"
              icon={
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2" />
                </svg>
              }
            />
            <StatCard
              title="Bekleyen"
              value={String(summary.pending)}
              variant="warning"
              icon={
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              }
            />
            <StatCard
              title="Sonuclanan"
              value={String(summary.resolved)}
              variant="success"
              icon={
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              }
            />
          </div>

          <div className="grid gap-4 sm:grid-cols-3">
            <StatCard
              title="Dogru Tahmin"
              value={String(summary.correct)}
              variant="success"
              icon={
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
              }
            />
            <StatCard
              title="Yanlis Tahmin"
              value={String(summary.wrong)}
              variant="error"
              icon={
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              }
            />
            <Card>
              <CardDescription>Basari Orani</CardDescription>
              <p className="mt-1 text-2xl font-black text-success">{toPercent(summary.accuracy, 1)}</p>
              <p className="mt-1 text-xs text-foreground-muted">
                Sadece sonuclanan tahminler ({summary.resolved}) ile hesaplanir.
              </p>
              <div className="mt-3">
                <Progress
                  value={summary.accuracy}
                  size="sm"
                  variant={summary.accuracy >= 60 ? "success" : summary.accuracy >= 40 ? "warning" : "error"}
                />
              </div>
            </Card>
          </div>

          <Card>
            <div className="mb-4 flex items-center justify-between gap-2">
              <div>
                <CardTitle>Market Basari Ozeti</CardTitle>
                <CardDescription>
                  Market sekmelerinde sonuclanan maclara gore basari orani gosterilir.
                </CardDescription>
              </div>
              <Badge variant="neutral" size="sm">
                Secili: {selectedMarketLabel}
              </Badge>
            </div>
            <div className="flex flex-wrap gap-2">
              {marketMetrics.map((metric) => (
                <button
                  key={metric.key}
                  type="button"
                  onClick={() => setSelectedMarket(metric.key)}
                  className={cn(
                    "inline-flex items-center gap-2 rounded-lg border px-3 py-2 text-xs font-bold uppercase tracking-wide transition-colors",
                    selectedMarket === metric.key
                      ? "border-accent bg-accent/15 text-accent"
                      : "border-card-border bg-background-secondary text-foreground-tertiary hover:border-accent/40 hover:text-accent"
                  )}
                >
                  <span>{metric.label}</span>
                  <span className="text-[10px] font-black">
                    {metric.resolved > 0
                      ? `${toPercent(metric.accuracy, 1)} (${metric.correct}/${metric.resolved})`
                      : "Sonuclanan yok"}
                  </span>
                </button>
              ))}
            </div>
          </Card>
        </>
      )}

      <Card>
        <div className="mb-4 flex items-center gap-2">
          <svg className="h-4 w-4 text-accent" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2.586a1 1 0 01-.293.707l-6.414 6.414a1 1 0 00-.293.707V17l-4 4v-6.586a1 1 0 00-.293-.707L3.293 7.293A1 1 0 013 6.586V4z" />
          </svg>
          <CardTitle>Filtreler</CardTitle>
        </div>

        <div className="grid gap-4 sm:grid-cols-3">
          <div className="space-y-2">
            <label className="text-sm font-medium text-foreground-secondary">Baslangic Tarihi</label>
            <input
              type="date"
              value={startDate}
              onChange={(event) => setStartDate(event.target.value)}
              className={cn(
                "w-full rounded-xl border border-white/[0.08] bg-white/[0.03] px-4 py-2.5 text-sm text-foreground-secondary",
                "focus:border-accent/30 focus:outline-none focus:ring-2 focus:ring-accent/30",
                "transition-all duration-200"
              )}
            />
          </div>

          <div className="space-y-2">
            <label className="text-sm font-medium text-foreground-secondary">Bitis Tarihi</label>
            <input
              type="date"
              value={endDate}
              onChange={(event) => setEndDate(event.target.value)}
              className={cn(
                "w-full rounded-xl border border-white/[0.08] bg-white/[0.03] px-4 py-2.5 text-sm text-foreground-secondary",
                "focus:border-accent/30 focus:outline-none focus:ring-2 focus:ring-accent/30",
                "transition-all duration-200"
              )}
            />
          </div>

          <div className="space-y-2">
            <label className="text-sm font-medium text-foreground-secondary">Sonuc Filtresi</label>
            <select
              value={correct}
              onChange={(event) => setCorrect(event.target.value)}
              className={cn(
                "w-full rounded-xl border border-white/[0.08] bg-white/[0.03] px-4 py-2.5 text-sm text-foreground-secondary",
                "focus:border-accent/30 focus:outline-none focus:ring-2 focus:ring-accent/30",
                "transition-all duration-200"
              )}
            >
              <option value="all">Tumu</option>
              <option value="true">Dogru</option>
              <option value="false">Yanlis</option>
            </select>
          </div>
        </div>
      </Card>

      {loading && (
        <div className="flex items-center justify-center py-12">
          <div className="flex items-center gap-3 text-foreground-tertiary">
            <svg className="h-5 w-5 animate-spin text-accent" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
            </svg>
            <span className="text-sm">Gecmis verisi yukleniyor...</span>
          </div>
        </div>
      )}

      {error && (
        <div className="flex items-start gap-3 rounded-2xl border border-error/20 bg-error/10 p-4">
          <svg className="mt-0.5 h-5 w-5 flex-shrink-0 text-error" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <div>
            <p className="text-sm font-medium text-error">Bir hata olustu</p>
            <p className="mt-1 text-xs text-error/70">{error}</p>
          </div>
        </div>
      )}

      {!loading && !error && (
        <Card className="overflow-hidden">
          <div className="mb-3 flex items-center justify-between gap-3">
            <div>
              <CardTitle>Sonuclanan Tahminler</CardTitle>
              <CardDescription>
                Tablo sadece sonuclanmis kayitlari gosterir. Bekleyenler ustteki ozet kartlarinda izlenir.
              </CardDescription>
            </div>
            <Badge variant="neutral" size="sm">
              {resolvedItems.length} kayit
            </Badge>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-white/[0.06]">
                  <th className="px-4 py-4 text-left text-xs font-semibold uppercase tracking-wider text-foreground-muted">Tarih</th>
                  <th className="px-4 py-4 text-left text-xs font-semibold uppercase tracking-wider text-foreground-muted">Mac</th>
                  <th className="px-4 py-4 text-left text-xs font-semibold uppercase tracking-wider text-foreground-muted">Market</th>
                  <th className="px-4 py-4 text-left text-xs font-semibold uppercase tracking-wider text-foreground-muted">Tahmin</th>
                  <th className="px-4 py-4 text-left text-xs font-semibold uppercase tracking-wider text-foreground-muted">Gercek Sonuc</th>
                  <th className="px-4 py-4 text-left text-xs font-semibold uppercase tracking-wider text-foreground-muted">Durum</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/[0.04]">
                {resolvedItems.map((item) => (
                  <tr key={item.prediction_id} className="transition-colors hover:bg-white/[0.02]">
                    <td className="whitespace-nowrap px-4 py-4 text-foreground-secondary">{formatDateTime(item.date)}</td>
                    <td className="px-4 py-4 font-medium text-foreground-primary">{item.match}</td>
                    <td className="px-4 py-4">
                      <Badge variant="neutral" size="sm">
                        {item.market_type}
                      </Badge>
                    </td>
                    <td className="px-4 py-4 text-foreground-tertiary">{item.predicted_outcome || "-"}</td>
                    <td className="px-4 py-4 text-foreground-tertiary">{item.actual_outcome || "-"}</td>
                    <td className="px-4 py-4">
                      <ResultBadge correct={item.was_correct} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {!resolvedItems.length && (
            <div className="py-12 text-center">
              <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-white/[0.04]">
                <svg className="h-8 w-8 text-foreground-muted" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9.172 16.172a4 4 0 015.656 0M9 10h.01M15 10h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              </div>
              <p className="text-sm text-foreground-secondary">Secili filtrede sonuclanmis kayit bulunamadi.</p>
            </div>
          )}
        </Card>
      )}
    </section>
  );
}
