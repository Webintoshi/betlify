"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { getHealth, triggerFetchToday, triggerUpdateStats, type HealthResponse } from "@/lib/api";

const LEAGUES = [
  { id: 203, name: "Türkiye Süper Lig" },
  { id: 39, name: "Premier League" },
  { id: 140, name: "La Liga" },
  { id: 135, name: "Serie A" },
  { id: 78, name: "Bundesliga" },
  { id: 61, name: "Ligue 1" },
  { id: 17, name: "UEFA Şampiyonlar Ligi" },
  { id: 679, name: "UEFA Avrupa Ligi" }
];

export default function SettingsPage() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [minimumConfidence, setMinimumConfidence] = useState<number>(60);
  const [minimumEv, setMinimumEv] = useState<number>(5);
  const [trackedLeagues, setTrackedLeagues] = useState<number[]>([203, 39, 140, 135, 78, 61]);
  const [statusMessage, setStatusMessage] = useState<string>("");
  const [busy, setBusy] = useState<boolean>(false);

  useEffect(() => {
    const load = async () => {
      try {
        const response = await getHealth();
        setHealth(response);
      } catch (error) {
        setStatusMessage(error instanceof Error ? error.message : "Sağlık verisi alınamadı.");
      }
    };
    void load();
  }, []);

  const toggleLeague = (id: number) => {
    setTrackedLeagues((current) => (current.includes(id) ? current.filter((item) => item !== id) : [...current, id]));
  };

  const runTask = async (task: "fetch" | "stats") => {
    setBusy(true);
    setStatusMessage("");
    try {
      if (task === "fetch") {
        await triggerFetchToday();
        setStatusMessage("Bugünün maçları çekme görevi tetiklendi.");
      } else {
        await triggerUpdateStats();
        setStatusMessage("İstatistik güncelleme görevi tetiklendi.");
      }
      const refresh = await getHealth();
      setHealth(refresh);
    } catch (error) {
      setStatusMessage(error instanceof Error ? error.message : "İşlem sırasında hata oluştu.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="space-y-6">
      <div>
        <p className="text-xs uppercase tracking-[0.2em] text-zinc-500">Ayarlar</p>
        <h1 className="mt-1 text-3xl font-bold text-white">Sistem Ayarları</h1>
      </div>

      <Card className="space-y-4">
        <CardTitle>Minimum Güven Eşiği: {minimumConfidence}</CardTitle>
        <input
          type="range"
          min={50}
          max={80}
          value={minimumConfidence}
          onChange={(event) => setMinimumConfidence(Number(event.target.value))}
          className="w-full"
        />
      </Card>

      <Card className="space-y-4">
        <CardTitle>Minimum EV Eşiği: %{minimumEv}</CardTitle>
        <input
          type="range"
          min={0}
          max={20}
          value={minimumEv}
          onChange={(event) => setMinimumEv(Number(event.target.value))}
          className="w-full"
        />
      </Card>

      <Card className="space-y-3">
        <CardTitle>Takip Edilen Ligler</CardTitle>
        <div className="grid gap-2 sm:grid-cols-2">
          {LEAGUES.map((league) => (
            <label key={league.id} className="flex items-center gap-2 rounded-lg bg-[#141420] px-3 py-2 text-sm text-zinc-300">
              <Checkbox checked={trackedLeagues.includes(league.id)} onChange={() => toggleLeague(league.id)} />
              <span>{league.name}</span>
            </label>
          ))}
        </div>
      </Card>

      <Card className="space-y-3">
        <CardTitle>API Key Durumu</CardTitle>
        <div className="grid gap-2 md:grid-cols-2">
          <p className="text-sm text-zinc-300">
            Supabase:{" "}
            <span className={health?.supabase_connected ? "text-emerald-300" : "text-red-300"}>
              {health?.supabase_connected ? "Bağlı" : "Bağlı değil"}
            </span>
          </p>
          <p className="text-sm text-zinc-300">
            API-Football:{" "}
            <span className={health?.api_keys.api_football ? "text-emerald-300" : "text-red-300"}>
              {health?.api_keys.api_football ? "Bağlı" : "Bağlı değil"}
            </span>
          </p>
          <p className="text-sm text-zinc-300">
            The Odds API:{" "}
            <span className={health?.api_keys.the_odds ? "text-emerald-300" : "text-red-300"}>
              {health?.api_keys.the_odds ? "Bağlı" : "Bağlı değil"}
            </span>
          </p>
          <p className="text-sm text-zinc-300">
            OpenWeather:{" "}
            <span className={health?.api_keys.openweather ? "text-emerald-300" : "text-amber-300"}>
              {health?.api_keys.openweather ? "Bağlı" : "Tanımsız"}
            </span>
          </p>
        </div>
      </Card>

      <Card className="space-y-3">
        <CardTitle>Manuel Tetikleme</CardTitle>
        <CardDescription>Bu butonlar scheduler dışında görevleri manuel başlatır.</CardDescription>
        <div className="flex flex-wrap gap-2">
          <Button disabled={busy} onClick={() => void runTask("fetch")}>
            Bugünün maçlarını çek
          </Button>
          <Button variant="secondary" disabled={busy} onClick={() => void runTask("stats")}>
            İstatistikleri güncelle
          </Button>
        </div>
        {statusMessage ? <p className="text-sm text-zinc-400">{statusMessage}</p> : null}
      </Card>
    </section>
  );
}
