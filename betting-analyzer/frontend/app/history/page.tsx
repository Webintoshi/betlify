"use client";

import { useEffect, useMemo, useState } from "react";
import { Card, CardDescription, CardTitle } from "@/components/ui/card";
import { getHistory, type HistoryItem, type HistoryResponse } from "@/lib/api";
import { formatDateTime, toPercent } from "@/lib/utils";

function StatCard({
  title,
  value
}: {
  title: string;
  value: string;
}) {
  return (
    <Card className="space-y-1">
      <CardDescription>{title}</CardDescription>
      <CardTitle className="text-xl font-bold text-white">{value}</CardTitle>
    </Card>
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
    () => ["all", ...Array.from(new Set(items.map((item) => item.market_type))).sort((a, b) => a.localeCompare(b))],
    [items]
  );

  return (
    <section className="space-y-6">
      <div>
        <p className="text-xs uppercase tracking-[0.2em] text-zinc-500">Geçmiş</p>
        <h1 className="mt-1 text-3xl font-bold text-white">Tahmin Sonuçları</h1>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard title="Toplam Tahmin" value={String(history?.summary.total_predictions ?? 0)} />
        <StatCard title="Doğru" value={String(history?.summary.correct_predictions ?? 0)} />
        <StatCard title="Yanlış" value={String(history?.summary.wrong_predictions ?? 0)} />
        <StatCard title="İsabet" value={toPercent(history?.summary.accuracy_percentage ?? 0, 1)} />
      </div>

      <Card className="grid gap-4 md:grid-cols-4">
        <label className="text-sm text-zinc-300">
          Başlangıç
          <input
            type="date"
            value={startDate}
            onChange={(event) => setStartDate(event.target.value)}
            className="mt-2 w-full rounded-xl border border-white/10 bg-[#141420] px-3 py-2 text-sm text-zinc-100"
          />
        </label>
        <label className="text-sm text-zinc-300">
          Bitiş
          <input
            type="date"
            value={endDate}
            onChange={(event) => setEndDate(event.target.value)}
            className="mt-2 w-full rounded-xl border border-white/10 bg-[#141420] px-3 py-2 text-sm text-zinc-100"
          />
        </label>
        <label className="text-sm text-zinc-300">
          Market
          <select
            value={marketType}
            onChange={(event) => setMarketType(event.target.value)}
            className="mt-2 w-full rounded-xl border border-white/10 bg-[#141420] px-3 py-2 text-sm text-zinc-100"
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
        </label>
        <label className="text-sm text-zinc-300">
          Sonuç
          <select
            value={correct}
            onChange={(event) => setCorrect(event.target.value)}
            className="mt-2 w-full rounded-xl border border-white/10 bg-[#141420] px-3 py-2 text-sm text-zinc-100"
          >
            <option value="all">Tümü</option>
            <option value="true">Doğru</option>
            <option value="false">Yanlış</option>
          </select>
        </label>
      </Card>

      {loading ? <p className="text-sm text-zinc-400">Geçmiş verisi yükleniyor...</p> : null}
      {error ? <p className="rounded-xl bg-red-900/20 p-3 text-sm text-red-300">{error}</p> : null}

      <Card className="overflow-x-auto">
        <table className="w-full min-w-[760px] text-sm">
          <thead className="text-left text-xs uppercase tracking-wide text-zinc-500">
            <tr>
              <th className="pb-2">Tarih</th>
              <th className="pb-2">Maç</th>
              <th className="pb-2">Market</th>
              <th className="pb-2">Sonuç</th>
              <th className="pb-2">Doğru mu</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.prediction_id} className="border-t border-white/5 text-zinc-300">
                <td className="py-2">{formatDateTime(item.date)}</td>
                <td className="py-2">{item.match}</td>
                <td className="py-2">{item.market_type}</td>
                <td className="py-2">{item.actual_outcome ?? "-"}</td>
                <td className="py-2">
                  {item.was_correct === null ? "Bekliyor" : item.was_correct ? "✅ Doğru" : "❌ Yanlış"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!loading && !items.length ? <p className="mt-3 text-sm text-zinc-500">Filtreye uygun kayıt yok.</p> : null}
      </Card>
    </section>
  );
}
