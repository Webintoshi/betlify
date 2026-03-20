"use client";

import { useEffect, useMemo, useState } from "react";
import { Card, CardDescription, CardTitle, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { getHistory, type HistoryItem, type HistoryResponse } from "@/lib/api";
import { formatDateTime, toPercent } from "@/lib/utils";
import { cn } from "@/lib/utils";

function StatCard({
  title,
  value,
  icon,
  trend
}: {
  title: string;
  value: string;
  icon: React.ReactNode;
  trend?: string;
}) {
  return (
    <Card hover className="relative overflow-hidden">
      <div className="absolute top-0 right-0 w-20 h-20 bg-gradient-to-br from-accent/5 to-transparent rounded-bl-full" />
      <div className="relative">
        <div className="flex items-center gap-2 mb-2 text-foreground-muted">
          {icon}
          <CardDescription>{title}</CardDescription>
        </div>
        <div className="text-2xl font-bold text-foreground-primary">{value}</div>
        {trend && (
          <p className="text-xs text-success mt-1">{trend}</p>
        )}
      </div>
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
        Doğru
      </Badge>
    );
  }
  
  return (
    <Badge variant="error" size="sm" dot>
      Yanlış
    </Badge>
  );
}

export default function HistoryPage() {
  const [history, setHistory] = useState<HistoryResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string>("");
  const [startDate, setStartDate] = useState<string>("");
  const [endDate, setEndDate] = useState<string>("");
  const [marketType, setMarketType] = useState<string>("all");
  const [correct, setCorrect] = useState<string>("all");

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      setError("");
      try {
        const response = await getHistory({
          startDate: startDate || undefined,
          endDate: endDate || undefined,
          marketType,
          correct
        });
        setHistory(response);
      } catch (requestError) {
        setError(requestError instanceof Error ? requestError.message : "Geçmiş verisi alınamadı.");
      } finally {
        setLoading(false);
      }
    };
    void load();
  }, [startDate, endDate, marketType, correct]);

  const items: HistoryItem[] = history?.items ?? [];
  const marketTypes = useMemo(
    () => [
      "all",
      ...Array.from(new Set(items.map((item) => item.market_type))).sort((a, b) =>
        a.localeCompare(b)
      )
    ],
    [items]
  );

  const accuracyRate = history?.summary.accuracy_percentage ?? 0;

  return (
    <section className="space-y-8 animate-fade-in">
      {/* Header */}
      <div>
        <div className="flex items-center gap-3 mb-2">
          <Badge variant="accent" size="sm">Geçmiş</Badge>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-foreground-muted">
            Betlify
          </p>
        </div>
        <h1 className="text-display-sm text-foreground-primary">
          Tahmin Sonuçları
        </h1>
        <p className="mt-1 text-sm text-foreground-tertiary">
          Geçmiş tahminlerinizin performans analizi
        </p>
      </div>

      {/* Stats */}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          title="Toplam Tahmin"
          value={String(history?.summary.total_predictions ?? 0)}
          icon={
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
            </svg>
          }
        />
        <StatCard
          title="Doğru Tahmin"
          value={String(history?.summary.correct_predictions ?? 0)}
          icon={
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          }
          trend="Başarı oranı"
        />
        <StatCard
          title="Yanlış Tahmin"
          value={String(history?.summary.wrong_predictions ?? 0)}
          icon={
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          }
        />
        <Card className="relative overflow-hidden">
          <div className="absolute top-0 right-0 w-20 h-20 bg-gradient-to-br from-success/10 to-transparent rounded-bl-full" />
          <div className="relative">
            <div className="flex items-center gap-2 mb-2 text-foreground-muted">
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
              </svg>
              <CardDescription>İsabet Oranı</CardDescription>
            </div>
            <div className="text-2xl font-bold text-success">
              {toPercent(accuracyRate, 1)}
            </div>
            <div className="mt-3">
              <Progress 
                value={accuracyRate} 
                variant={accuracyRate >= 60 ? "success" : accuracyRate >= 40 ? "warning" : "error"}
                size="sm"
              />
            </div>
          </div>
        </Card>
      </div>

      {/* Filters */}
      <Card>
        <div className="flex items-center gap-2 mb-4">
          <svg className="w-4 h-4 text-accent" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2.586a1 1 0 01-.293.707l-6.414 6.414a1 1 0 00-.293.707V17l-4 4v-6.586a1 1 0 00-.293-.707L3.293 7.293A1 1 0 013 6.586V4z" />
          </svg>
          <CardTitle>Filtreler</CardTitle>
        </div>
        
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <div className="space-y-2">
            <label className="text-sm font-medium text-foreground-secondary">
              Başlangıç Tarihi
            </label>
            <input
              type="date"
              value={startDate}
              onChange={(event) => setStartDate(event.target.value)}
              className={cn(
                "w-full rounded-xl border border-white/[0.08] bg-white/[0.03] px-4 py-2.5 text-sm text-foreground-secondary",
                "focus:outline-none focus:ring-2 focus:ring-accent/30 focus:border-accent/30",
                "transition-all duration-200"
              )}
            />
          </div>
          
          <div className="space-y-2">
            <label className="text-sm font-medium text-foreground-secondary">
              Bitiş Tarihi
            </label>
            <input
              type="date"
              value={endDate}
              onChange={(event) => setEndDate(event.target.value)}
              className={cn(
                "w-full rounded-xl border border-white/[0.08] bg-white/[0.03] px-4 py-2.5 text-sm text-foreground-secondary",
                "focus:outline-none focus:ring-2 focus:ring-accent/30 focus:border-accent/30",
                "transition-all duration-200"
              )}
            />
          </div>
          
          <div className="space-y-2">
            <label className="text-sm font-medium text-foreground-secondary">
              Market Türü
            </label>
            <select
              value={marketType}
              onChange={(event) => setMarketType(event.target.value)}
              className={cn(
                "w-full rounded-xl border border-white/[0.08] bg-white/[0.03] px-4 py-2.5 text-sm text-foreground-secondary",
                "focus:outline-none focus:ring-2 focus:ring-accent/30 focus:border-accent/30",
                "transition-all duration-200"
              )}
            >
              <option value="all">Tümü</option>
              {marketTypes
                .filter((item) => item !== "all")
                .map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
            </select>
          </div>
          
          <div className="space-y-2">
            <label className="text-sm font-medium text-foreground-secondary">
              Sonuç
            </label>
            <select
              value={correct}
              onChange={(event) => setCorrect(event.target.value)}
              className={cn(
                "w-full rounded-xl border border-white/[0.08] bg-white/[0.03] px-4 py-2.5 text-sm text-foreground-secondary",
                "focus:outline-none focus:ring-2 focus:ring-accent/30 focus:border-accent/30",
                "transition-all duration-200"
              )}
            >
              <option value="all">Tümü</option>
              <option value="true">Doğru</option>
              <option value="false">Yanlış</option>
            </select>
          </div>
        </div>
      </Card>

      {/* Loading State */}
      {loading && (
        <div className="flex items-center justify-center py-12">
          <div className="flex items-center gap-3 text-foreground-tertiary">
            <svg className="animate-spin h-5 w-5 text-accent" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
            </svg>
            <span className="text-sm">Geçmiş verisi yükleniyor...</span>
          </div>
        </div>
      )}

      {/* Error State */}
      {error && (
        <div className="rounded-2xl bg-error/10 border border-error/20 p-4 flex items-start gap-3">
          <svg className="w-5 h-5 text-error flex-shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <div>
            <p className="text-sm font-medium text-error">Bir hata oluştu</p>
            <p className="text-xs text-error/70 mt-1">{error}</p>
          </div>
        </div>
      )}

      {/* History Table */}
      {!loading && !error && (
        <Card className="overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-white/[0.06]">
                  <th className="text-left py-4 px-4 text-xs font-semibold uppercase tracking-wider text-foreground-muted">
                    Tarih
                  </th>
                  <th className="text-left py-4 px-4 text-xs font-semibold uppercase tracking-wider text-foreground-muted">
                    Maç
                  </th>
                  <th className="text-left py-4 px-4 text-xs font-semibold uppercase tracking-wider text-foreground-muted">
                    Market
                  </th>
                  <th className="text-left py-4 px-4 text-xs font-semibold uppercase tracking-wider text-foreground-muted">
                    Sonuç
                  </th>
                  <th className="text-left py-4 px-4 text-xs font-semibold uppercase tracking-wider text-foreground-muted">
                    Durum
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/[0.04]">
                {items.map((item) => (
                  <tr 
                    key={item.prediction_id} 
                    className="hover:bg-white/[0.02] transition-colors"
                  >
                    <td className="py-4 px-4 text-foreground-secondary whitespace-nowrap">
                      {formatDateTime(item.date)}
                    </td>
                    <td className="py-4 px-4 text-foreground-primary font-medium">
                      {item.match}
                    </td>
                    <td className="py-4 px-4">
                      <Badge variant="neutral" size="sm">
                        {item.market_type}
                      </Badge>
                    </td>
                    <td className="py-4 px-4 text-foreground-tertiary">
                      {item.actual_outcome ?? "-"}
                    </td>
                    <td className="py-4 px-4">
                      <ResultBadge correct={item.was_correct} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          
          {!items.length && (
            <div className="text-center py-12">
              <div className="w-16 h-16 rounded-full bg-white/[0.04] flex items-center justify-center mx-auto mb-4">
                <svg className="w-8 h-8 text-foreground-muted" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9.172 16.172a4 4 0 015.656 0M9 10h.01M15 10h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              </div>
              <p className="text-sm text-foreground-secondary">
                Filtreye uygun kayıt bulunamadı.
              </p>
            </div>
          )}
        </Card>
      )}
    </section>
  );
}
