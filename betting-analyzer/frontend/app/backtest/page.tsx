"use client";

import { useEffect, useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Card, CardDescription, CardTitle } from "@/components/ui/card";
import {
  getBacktestDataset,
  getBacktestStatus,
  startBacktestRun,
  type BacktestDatasetResponse,
  type BacktestResultRow,
  type BacktestStatusResponse
} from "@/lib/api";
import { cn, formatDateTime, toPercent } from "@/lib/utils";

function toInputDate(value: Date): string {
  const year = value.getFullYear();
  const month = `${value.getMonth() + 1}`.padStart(2, "0");
  const day = `${value.getDate()}`.padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function StatCard({ title, value, subtitle }: { title: string; value: string; subtitle: string }) {
  return (
    <Card hover>
      <CardDescription className="uppercase tracking-wide">{title}</CardDescription>
      <div className="mt-2 text-3xl font-black text-foreground-primary tracking-tight">{value}</div>
      <p className="mt-2 text-xs font-bold text-foreground-muted uppercase tracking-wide">{subtitle}</p>
    </Card>
  );
}

function HitBadge({ hit }: { hit: boolean | null }) {
  if (hit === null) {
    return <Badge variant="neutral" size="sm">N/A</Badge>;
  }
  if (hit) {
    return <Badge variant="success" size="sm">DOGRU</Badge>;
  }
  return <Badge variant="error" size="sm">YANLIS</Badge>;
}

export default function BacktestPage() {
  const [startDate, setStartDate] = useState<string>("");
  const [endDate, setEndDate] = useState<string>("");
  const [daysBack, setDaysBack] = useState<number>(30);
  const [league, setLeague] = useState<string>("");
  const [minConfidence, setMinConfidence] = useState<number>(51);
  const [maxMatches, setMaxMatches] = useState<number>(300);
  const [includeNonRecommended, setIncludeNonRecommended] = useState<boolean>(true);

  const [dataset, setDataset] = useState<BacktestDatasetResponse | null>(null);
  const [status, setStatus] = useState<BacktestStatusResponse | null>(null);
  const [loadingDataset, setLoadingDataset] = useState<boolean>(false);
  const [loadingRun, setLoadingRun] = useState<boolean>(false);
  const [error, setError] = useState<string>("");

  useEffect(() => {
    const today = new Date();
    const start = new Date(today);
    start.setDate(today.getDate() - 29);
    setStartDate(toInputDate(start));
    setEndDate(toInputDate(today));
  }, []);

  useEffect(() => {
    let mounted = true;

    const loadStatus = async () => {
      try {
        const next = await getBacktestStatus();
        if (mounted) {
          setStatus(next);
        }
      } catch {
        // sessiz gec
      }
    };

    void loadStatus();
    const interval = window.setInterval(() => {
      void loadStatus();
    }, 4000);

    return () => {
      mounted = false;
      window.clearInterval(interval);
    };
  }, []);

  const progress = useMemo(() => {
    if (!status || status.total_matches_scanned <= 0) {
      return 0;
    }
    return Math.min(100, Math.round((status.processed / status.total_matches_scanned) * 100));
  }, [status]);

  const rows: BacktestResultRow[] = status?.rows ?? [];

  const loadDataset = async () => {
    setLoadingDataset(true);
    setError("");
    try {
      const payload = await getBacktestDataset({
        daysBack,
        startDate: startDate || undefined,
        endDate: endDate || undefined,
        league: league || undefined,
        maxMatches,
        previewLimit: 100
      });
      setDataset(payload);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Dataset alinamadi.");
    } finally {
      setLoadingDataset(false);
    }
  };

  const startRun = async () => {
    setLoadingRun(true);
    setError("");
    try {
      await startBacktestRun({
        days_back: daysBack,
        start_date: startDate || undefined,
        end_date: endDate || undefined,
        league: league || undefined,
        min_confidence: minConfidence,
        include_non_recommended: includeNonRecommended,
        max_matches: maxMatches,
        store_rows: 600
      });
      const next = await getBacktestStatus();
      setStatus(next);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Backtest baslatilamadi.");
    } finally {
      setLoadingRun(false);
    }
  };

  return (
    <section className="space-y-8 animate-fade-in">
      <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4 pb-6 border-b-2 border-card-border">
        <div>
          <div className="flex items-center gap-3 mb-2">
            <Badge variant="accent" size="sm">LAB</Badge>
            <p className="text-xs font-black uppercase tracking-[0.3em] text-accent">Betlify</p>
          </div>
          <h1 className="text-display-sm text-foreground-primary uppercase tracking-tight">Backtest Motor Laboratuvari</h1>
          <p className="mt-1 text-sm font-bold text-foreground-muted uppercase tracking-wide">
            Gecmis maclari oynanmamis gibi analiz et, gercek skorla karsilastir
          </p>
        </div>
        <Badge variant={status?.running ? "warning" : "neutral"} size="md" dot>
          {status?.running ? "Calisiyor" : status?.status ? `Durum: ${status.status}` : "Hazir"}
        </Badge>
      </div>

      <Card>
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <div className="space-y-2">
            <label className="text-xs font-black uppercase tracking-wide text-foreground-tertiary">Baslangic</label>
            <input
              type="date"
              value={startDate}
              onChange={(event) => setStartDate(event.target.value)}
              className="w-full rounded-lg border-2 border-card-border bg-background-secondary px-4 py-3 text-sm font-bold text-foreground-primary"
            />
          </div>
          <div className="space-y-2">
            <label className="text-xs font-black uppercase tracking-wide text-foreground-tertiary">Bitis</label>
            <input
              type="date"
              value={endDate}
              onChange={(event) => setEndDate(event.target.value)}
              className="w-full rounded-lg border-2 border-card-border bg-background-secondary px-4 py-3 text-sm font-bold text-foreground-primary"
            />
          </div>
          <div className="space-y-2">
            <label className="text-xs font-black uppercase tracking-wide text-foreground-tertiary">Gun Sayisi</label>
            <input
              type="number"
              min={3}
              max={365}
              value={daysBack}
              onChange={(event) => setDaysBack(Number(event.target.value || 30))}
              className="w-full rounded-lg border-2 border-card-border bg-background-secondary px-4 py-3 text-sm font-bold text-foreground-primary"
            />
          </div>
          <div className="space-y-2">
            <label className="text-xs font-black uppercase tracking-wide text-foreground-tertiary">Lig filtresi (ops.)</label>
            <input
              type="text"
              placeholder="Eredivisie"
              value={league}
              onChange={(event) => setLeague(event.target.value)}
              className="w-full rounded-lg border-2 border-card-border bg-background-secondary px-4 py-3 text-sm font-bold text-foreground-primary"
            />
          </div>
        </div>

        <div className="grid gap-4 md:grid-cols-3 mt-4">
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <label className="text-xs font-black uppercase tracking-wide text-foreground-tertiary">Min Confidence</label>
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
          </div>
          <div className="space-y-2">
            <label className="text-xs font-black uppercase tracking-wide text-foreground-tertiary">Max mac</label>
            <input
              type="number"
              min={20}
              max={3000}
              value={maxMatches}
              onChange={(event) => setMaxMatches(Number(event.target.value || 300))}
              className="w-full rounded-lg border-2 border-card-border bg-background-secondary px-4 py-3 text-sm font-bold text-foreground-primary"
            />
          </div>
          <div className="flex items-end">
            <label className="inline-flex items-center gap-3 text-sm font-bold text-foreground-secondary">
              <input
                type="checkbox"
                checked={includeNonRecommended}
                onChange={(event) => setIncludeNonRecommended(event.target.checked)}
                className="w-4 h-4 rounded border-card-border bg-background-secondary"
              />
              Onerilmeyenleri de rapora dahil et
            </label>
          </div>
        </div>

        <div className="flex flex-wrap gap-3 mt-6">
          <button
            type="button"
            onClick={() => void loadDataset()}
            disabled={loadingDataset || loadingRun}
            className={cn(
              "rounded-lg px-4 py-2.5 text-sm font-black uppercase tracking-wide border-2 transition-all",
              "border-card-border text-foreground-secondary hover:border-accent hover:text-accent",
              (loadingDataset || loadingRun) && "opacity-50 cursor-not-allowed"
            )}
          >
            {loadingDataset ? "Onizleme aliniyor..." : "Dataset Onizleme"}
          </button>
          <button
            type="button"
            onClick={() => void startRun()}
            disabled={loadingRun || status?.running}
            className={cn(
              "rounded-lg px-4 py-2.5 text-sm font-black uppercase tracking-wide border-2 transition-all",
              "border-accent bg-accent text-white hover:brightness-110",
              (loadingRun || status?.running) && "opacity-50 cursor-not-allowed"
            )}
          >
            {loadingRun || status?.running ? "Backtest Calisiyor..." : "Backtest Baslat"}
          </button>
        </div>

        {!!error && (
          <p className="mt-4 text-sm font-bold text-error-bright">{error}</p>
        )}
      </Card>

      {status && (
        <Card>
          <div className="flex items-center justify-between gap-4">
            <CardTitle>Calisma Durumu</CardTitle>
            <Badge variant={status.running ? "warning" : "neutral"} size="sm">
              %{progress}
            </Badge>
          </div>
          <div className="mt-3 h-2 rounded bg-card-border overflow-hidden">
            <div className="h-full bg-accent transition-all" style={{ width: `${progress}%` }} />
          </div>
          <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-4 text-xs font-bold text-foreground-muted uppercase tracking-wide">
            <span>Islenen: {status.processed}</span>
            <span>Taranan: {status.total_matches_scanned}</span>
            <span>Basarili: {status.success}</span>
            <span>Hata: {status.failed}</span>
            <span>Odds yok: {status.skipped_no_odds}</span>
            <span>Market yok: {status.skipped_no_market}</span>
            <span>Baslangic: {status.started_at ? formatDateTime(status.started_at) : "-"}</span>
            <span>Bitis: {status.finished_at ? formatDateTime(status.finished_at) : "-"}</span>
          </div>
        </Card>
      )}

      {status?.summary && (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <StatCard title="Tahmin" value={String(status.summary.total_predictions)} subtitle="Uretilen satir" />
          <StatCard title="Hit Rate" value={toPercent(status.summary.hit_rate_pct, 1)} subtitle="Degerlendirilenlerde" />
          <StatCard title="ROI" value={toPercent(status.summary.roi_pct, 2)} subtitle="Birim bazli" />
          <StatCard title="Ortalama EV" value={toPercent(status.summary.avg_ev * 100, 2)} subtitle="Secilen marketler" />
        </div>
      )}

      {!!status && status.status === "completed" && (status.summary?.total_predictions ?? 0) === 0 && (
        <Card>
          <p className="text-sm font-black text-warning-bright uppercase tracking-wide">
            Backtest tamamlandi ama tahmin uretilemedi
          </p>
          <p className="mt-2 text-xs font-bold text-foreground-muted uppercase tracking-wide">
            Olasi neden: secilen pencerede backteste uygun odds/market yok.
          </p>
          <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-4 text-xs font-bold text-foreground-muted uppercase tracking-wide">
            <span>Taranan: {status.total_matches_scanned}</span>
            <span>Odds olmayan: {status.skipped_no_odds}</span>
            <span>Market cikmayan: {status.skipped_no_market}</span>
            <span>Hata: {status.failed}</span>
          </div>
        </Card>
      )}

      {dataset && (
        <Card>
          <div className="flex items-center justify-between">
            <CardTitle>Dataset Onizleme</CardTitle>
            <Badge variant="neutral" size="sm">
              {dataset.matches_with_odds}/{dataset.total_matches_scanned} oddsli mac
            </Badge>
          </div>
          <p className="mt-2 text-xs font-bold text-foreground-muted uppercase tracking-wide">
            Pencere: {dataset.window.start_date} - {dataset.window.end_date}
          </p>
          <div className="overflow-x-auto mt-4">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-card-border">
                  <th className="text-left py-3 px-2 text-xs font-black uppercase tracking-wide text-foreground-tertiary">Tarih</th>
                  <th className="text-left py-3 px-2 text-xs font-black uppercase tracking-wide text-foreground-tertiary">Mac</th>
                  <th className="text-left py-3 px-2 text-xs font-black uppercase tracking-wide text-foreground-tertiary">Lig</th>
                  <th className="text-left py-3 px-2 text-xs font-black uppercase tracking-wide text-foreground-tertiary">Skor</th>
                  <th className="text-left py-3 px-2 text-xs font-black uppercase tracking-wide text-foreground-tertiary">Odds</th>
                </tr>
              </thead>
              <tbody>
                {dataset.preview.map((row) => (
                  <tr key={row.match_id} className="border-b border-card-border/40">
                    <td className="py-2 px-2 text-foreground-secondary">{formatDateTime(row.match_date)}</td>
                    <td className="py-2 px-2 text-foreground-primary font-bold">{row.home_team} - {row.away_team}</td>
                    <td className="py-2 px-2 text-foreground-muted">{row.league}</td>
                    <td className="py-2 px-2 text-foreground-muted">{row.score}</td>
                    <td className="py-2 px-2">
                      <Badge variant={row.has_odds ? "success" : "error"} size="sm">{row.has_odds ? "VAR" : "YOK"}</Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {!!rows.length && (
        <Card>
          <div className="flex items-center justify-between">
            <CardTitle>Backtest Sonuclari</CardTitle>
            <Badge variant="neutral" size="sm">{rows.length} satir</Badge>
          </div>
          <div className="overflow-x-auto mt-4">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-card-border">
                  <th className="text-left py-3 px-2 text-xs font-black uppercase tracking-wide text-foreground-tertiary">Tarih</th>
                  <th className="text-left py-3 px-2 text-xs font-black uppercase tracking-wide text-foreground-tertiary">Mac</th>
                  <th className="text-left py-3 px-2 text-xs font-black uppercase tracking-wide text-foreground-tertiary">Market</th>
                  <th className="text-left py-3 px-2 text-xs font-black uppercase tracking-wide text-foreground-tertiary">Olasilik</th>
                  <th className="text-left py-3 px-2 text-xs font-black uppercase tracking-wide text-foreground-tertiary">Oran</th>
                  <th className="text-left py-3 px-2 text-xs font-black uppercase tracking-wide text-foreground-tertiary">EV</th>
                  <th className="text-left py-3 px-2 text-xs font-black uppercase tracking-wide text-foreground-tertiary">Guven</th>
                  <th className="text-left py-3 px-2 text-xs font-black uppercase tracking-wide text-foreground-tertiary">Skor</th>
                  <th className="text-left py-3 px-2 text-xs font-black uppercase tracking-wide text-foreground-tertiary">Hit</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={`${row.match_id}-${row.our_market}`} className="border-b border-card-border/40">
                    <td className="py-2 px-2 text-foreground-secondary">{formatDateTime(row.date)}</td>
                    <td className="py-2 px-2">
                      <p className="font-bold text-foreground-primary">{row.home_team} - {row.away_team}</p>
                      <p className="text-xs text-foreground-muted">{row.league}</p>
                    </td>
                    <td className="py-2 px-2"><Badge variant="neutral" size="sm">{row.our_market}</Badge></td>
                    <td className="py-2 px-2 text-foreground-secondary">%{(row.our_probability * 100).toFixed(1)}</td>
                    <td className="py-2 px-2 text-foreground-secondary">{row.our_odd.toFixed(2)}</td>
                    <td className={cn("py-2 px-2 font-bold", row.our_ev >= 0 ? "text-success-bright" : "text-error-bright")}>
                      %{(row.our_ev * 100).toFixed(2)}
                    </td>
                    <td className="py-2 px-2 text-foreground-secondary">%{row.confidence_score.toFixed(1)}</td>
                    <td className="py-2 px-2 text-foreground-secondary">{row.score}</td>
                    <td className="py-2 px-2"><HitBadge hit={row.hit} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </section>
  );
}
