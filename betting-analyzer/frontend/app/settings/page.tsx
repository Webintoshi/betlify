"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardTitle, CardHeader, CardContent, CardFooter } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { Progress } from "@/components/ui/progress";
import { getHealth, triggerFetchToday, triggerUpdateStats, type HealthResponse } from "@/lib/api";
import { cn } from "@/lib/utils";

const LEAGUES = [
  { id: 203, name: "Türkiye Süper Lig", flag: "🇹🇷" },
  { id: 39, name: "Premier League", flag: "🏴󠁧󠁢󠁥󠁮󠁧󠁿" },
  { id: 140, name: "La Liga", flag: "🇪🇸" },
  { id: 135, name: "Serie A", flag: "🇮🇹" },
  { id: 78, name: "Bundesliga", flag: "🇩🇪" },
  { id: 61, name: "Ligue 1", flag: "🇫🇷" },
  { id: 17, name: "UEFA Şampiyonlar Ligi", flag: "🏆" },
  { id: 679, name: "UEFA Avrupa Ligi", flag: "🏆" }
];

function ApiStatusBadge({ connected }: { connected: boolean }) {
  return connected ? (
    <Badge variant="success" size="sm" dot>Bağlı</Badge>
  ) : (
    <Badge variant="error" size="sm" dot>Bağlı Değil</Badge>
  );
}

function ApiStatusRow({ 
  name, 
  connected, 
  description 
}: { 
  name: string; 
  connected: boolean;
  description?: string;
}) {
  return (
    <div className="flex items-center justify-between py-3 px-4 rounded-xl bg-white/[0.02] border border-white/[0.04] hover:border-white/[0.08] transition-colors">
      <div>
        <p className="text-sm font-medium text-foreground-secondary">{name}</p>
        {description && (
          <p className="text-xs text-foreground-muted mt-0.5">{description}</p>
        )}
      </div>
      <ApiStatusBadge connected={connected} />
    </div>
  );
}

export default function SettingsPage() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [minimumConfidence, setMinimumConfidence] = useState<number>(60);
  const [minimumEv, setMinimumEv] = useState<number>(5);
  const [trackedLeagues, setTrackedLeagues] = useState<number[]>([203, 39, 140, 135, 78, 61]);
  const [statusMessage, setStatusMessage] = useState<string>("");
  const [messageType, setMessageType] = useState<"success" | "error">("success");
  const [busy, setBusy] = useState<boolean>(false);

  useEffect(() => {
    const load = async () => {
      try {
        const response = await getHealth();
        setHealth(response);
      } catch (error) {
        setStatusMessage(error instanceof Error ? error.message : "Sağlık verisi alınamadı.");
        setMessageType("error");
      }
    };
    void load();
  }, []);

  const toggleLeague = (id: number) => {
    setTrackedLeagues((current) =>
      current.includes(id) ? current.filter((item) => item !== id) : [...current, id]
    );
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
      setMessageType("success");
      const refresh = await getHealth();
      setHealth(refresh);
    } catch (error) {
      setStatusMessage(error instanceof Error ? error.message : "İşlem sırasında hata oluştu.");
      setMessageType("error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="space-y-8 animate-fade-in">
      {/* Header */}
      <div>
        <div className="flex items-center gap-3 mb-2">
          <Badge variant="accent" size="sm">Ayarlar</Badge>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-foreground-muted">
            Betlify
          </p>
        </div>
        <h1 className="text-display-sm text-foreground-primary">
          Sistem Ayarları
        </h1>
        <p className="mt-1 text-sm text-foreground-tertiary">
          Uygulama tercihlerinizi ve API bağlantılarını yönetin
        </p>
      </div>

      {/* Message */}
      {statusMessage && (
        <div className={cn(
          "rounded-xl p-4 flex items-start gap-3",
          messageType === "success" 
            ? "bg-success/10 border border-success/20" 
            : "bg-error/10 border border-error/20"
        )}>
          <svg 
            className={cn(
              "w-5 h-5 flex-shrink-0 mt-0.5",
              messageType === "success" ? "text-success" : "text-error"
            )} 
            fill="none" 
            viewBox="0 0 24 24" 
            stroke="currentColor"
          >
            {messageType === "success" ? (
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            ) : (
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            )}
          </svg>
          <p className={cn(
            "text-sm",
            messageType === "success" ? "text-success" : "text-error"
          )}>
            {statusMessage}
          </p>
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Left Column */}
        <div className="space-y-6">
          {/* Confidence Threshold */}
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <svg className="w-5 h-5 text-accent" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  <CardTitle>Minimum Güven Eşiği</CardTitle>
                </div>
                <Badge variant="accent" size="sm">{minimumConfidence}%</Badge>
              </div>
              <CardDescription>
                Bu eşiğin altındaki tahminler gösterilmeyecek
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                <input
                  type="range"
                  min={50}
                  max={80}
                  value={minimumConfidence}
                  onChange={(event) => setMinimumConfidence(Number(event.target.value))}
                  className="w-full"
                />
                <div className="flex justify-between text-xs text-foreground-muted">
                  <span>50%</span>
                  <span>65%</span>
                  <span>80%</span>
                </div>
                <Progress 
                  value={(minimumConfidence - 50) / 30 * 100} 
                  variant={minimumConfidence >= 70 ? "success" : minimumConfidence >= 60 ? "warning" : "default"}
                  size="sm"
                />
              </div>
            </CardContent>
          </Card>

          {/* EV Threshold */}
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <svg className="w-5 h-5 text-accent" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
                  </svg>
                  <CardTitle>Minimum EV Eşiği</CardTitle>
                </div>
                <Badge variant="accent" size="sm">%{minimumEv}</Badge>
              </div>
              <CardDescription>
                Expected Value (Beklenen Değer) filtresi
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                <input
                  type="range"
                  min={0}
                  max={20}
                  value={minimumEv}
                  onChange={(event) => setMinimumEv(Number(event.target.value))}
                  className="w-full"
                />
                <div className="flex justify-between text-xs text-foreground-muted">
                  <span>0%</span>
                  <span>10%</span>
                  <span>20%</span>
                </div>
                <Progress 
                  value={minimumEv / 20 * 100} 
                  variant={minimumEv >= 10 ? "success" : minimumEv >= 5 ? "warning" : "default"}
                  size="sm"
                />
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Right Column */}
        <div className="space-y-6">
          {/* Tracked Leagues */}
          <Card>
            <CardHeader>
              <div className="flex items-center gap-2">
                <svg className="w-5 h-5 text-accent" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3.055 11H5a2 2 0 012 2v1a2 2 0 002 2 2 2 0 012 2v2.945M8 3.935V5.5A2.5 2.5 0 0010.5 8h.5a2 2 0 012 2 2 2 0 104 0 2 2 0 012-2h1.064M15 20.488V18a2 2 0 012-2h3.064M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <CardTitle>Takip Edilen Ligler</CardTitle>
              </div>
              <CardDescription>
                Analiz edilecek ligleri seçin ({trackedLeagues.length}/{LEAGUES.length})
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid gap-2 sm:grid-cols-2">
                {LEAGUES.map((league) => (
                  <label
                    key={league.id}
                    className={cn(
                      "flex items-center gap-3 p-3 rounded-xl border transition-all duration-200 cursor-pointer",
                      trackedLeagues.includes(league.id)
                        ? "bg-accent/10 border-accent/30"
                        : "bg-white/[0.02] border-white/[0.04] hover:border-white/[0.08]"
                    )}
                  >
                    <Checkbox
                      checked={trackedLeagues.includes(league.id)}
                      onChange={() => toggleLeague(league.id)}
                      variant="accent"
                    />
                    <span className="text-lg">{league.flag}</span>
                    <span className={cn(
                      "text-sm",
                      trackedLeagues.includes(league.id) 
                        ? "text-foreground-primary font-medium" 
                        : "text-foreground-tertiary"
                    )}>
                      {league.name}
                    </span>
                  </label>
                ))}
              </div>
            </CardContent>
          </Card>

          {/* API Status */}
          <Card>
            <CardHeader>
              <div className="flex items-center gap-2">
                <svg className="w-5 h-5 text-accent" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2m-2-4h.01M17 16h.01" />
                </svg>
                <CardTitle>API Bağlantı Durumu</CardTitle>
              </div>
              <CardDescription>
                Harici servislerin bağlantı durumları
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-2">
              <ApiStatusRow 
                name="Supabase" 
                connected={health?.supabase_connected ?? false}
                description="Veritabanı bağlantısı"
              />
              <ApiStatusRow 
                name="API-Football" 
                connected={health?.api_keys.api_football ?? false}
                description="Maç verileri ve istatistikler"
              />
              <ApiStatusRow 
                name="The Odds API" 
                connected={health?.api_keys.the_odds ?? false}
                description="Oran verileri"
              />
              <ApiStatusRow 
                name="OpenWeather" 
                connected={health?.api_keys.openweather ?? false}
                description="Hava durumu verileri"
              />
            </CardContent>
          </Card>
        </div>
      </div>

      {/* Manual Tasks */}
      <Card variant="elevated">
        <CardHeader>
          <div className="flex items-center gap-2">
            <svg className="w-5 h-5 text-accent" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <CardTitle>Manuel Tetikleme</CardTitle>
          </div>
          <CardDescription>
            Scheduler dışında görevleri manuel başlatın
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap gap-3">
            <Button 
              disabled={busy} 
              onClick={() => void runTask("fetch")}
              size="lg"
            >
              {busy ? (
                <svg className="animate-spin -ml-1 mr-2 h-4 w-4" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                </svg>
              ) : (
                <svg className="w-4 h-4 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                </svg>
              )}
              Bugünün Maçlarını Çek
            </Button>
            <Button 
              variant="secondary" 
              disabled={busy} 
              onClick={() => void runTask("stats")}
              size="lg"
            >
              <svg className="w-4 h-4 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
              </svg>
              İstatistikleri Güncelle
            </Button>
          </div>
        </CardContent>
      </Card>
    </section>
  );
}
