"use client";

import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardTitle, CardHeader, CardContent, CardFooter } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { createCoupon } from "@/lib/api";
import {
  calculateTotalOdds,
  clearCouponSelections,
  getCouponSelections,
  removeCouponSelection,
  type CouponSelection
} from "@/lib/coupon-store";
import { cn } from "@/lib/utils";

function EmptyState({ onClear }: { onClear: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center py-12 text-center">
      <div className="w-20 h-20 rounded-2xl bg-white/[0.04] border border-white/[0.06] flex items-center justify-center mb-4">
        <svg className="w-10 h-10 text-foreground-muted" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 5v2m0 4v2m0 4v2M5 5a2 2 0 00-2 2v3a2 2 0 110 4v3a2 2 0 002 2h14a2 2 0 002-2v-3a2 2 0 110-4V7a2 2 0 00-2-2H5z" />
        </svg>
      </div>
      <h3 className="text-lg font-semibold text-foreground-primary mb-1">
        Kuponunuz Boş
      </h3>
      <p className="text-sm text-foreground-tertiary max-w-xs mb-4">
        Dashboard veya Maç Detay sayfalarından seçim ekleyerek kupon oluşturabilirsiniz.
      </p>
      <Button variant="outline" size="sm" onClick={onClear}>
        Dashboard&apos;a Git
      </Button>
    </div>
  );
}

export default function CouponPage() {
  const [selections, setSelections] = useState<CouponSelection[]>([]);
  const [saving, setSaving] = useState<boolean>(false);
  const [message, setMessage] = useState<string>("");
  const [messageType, setMessageType] = useState<"success" | "error">("success");

  const totalOdds = useMemo(() => calculateTotalOdds(selections), [selections]);
  const potentialWin = useMemo(() => totalOdds * 100, [totalOdds]); // 100 TL varsayılan bahis

  useEffect(() => {
    setSelections(getCouponSelections());
  }, []);

  const handleRemove = (matchId: string) => {
    setSelections(removeCouponSelection(matchId));
    setMessage("");
  };

  const handleClear = () => {
    clearCouponSelections();
    setSelections([]);
    setMessage("Kupon temizlendi.");
    setMessageType("success");
  };

  const handleSave = async () => {
    if (!selections.length) {
      setMessage("Kaydedilecek seçim yok.");
      setMessageType("error");
      return;
    }
    setSaving(true);
    setMessage("");
    try {
      const response = await createCoupon(selections);
      setMessage(`Kupon kaydedildi. Kod: ${response.coupon_id}`);
      setMessageType("success");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Kupon kaydedilemedi.");
      setMessageType("error");
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="space-y-8 animate-fade-in">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4">
        <div>
          <div className="flex items-center gap-3 mb-2">
            <Badge variant="accent" size="sm">Kupon</Badge>
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-foreground-muted">
              Betlify
            </p>
          </div>
          <h1 className="text-display-sm text-foreground-primary">
            Kupon Oluştur
          </h1>
          <p className="mt-1 text-sm text-foreground-tertiary">
            Seçimlerinizi yönetin ve kupon kaydedin
          </p>
        </div>
        {selections.length > 0 && (
          <Button
            variant="outline"
            size="sm"
            onClick={handleClear}
            className="text-error hover:text-error hover:bg-error/10 border-error/30"
          >
            <svg className="w-4 h-4 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
            </svg>
            Temizle
          </Button>
        )}
      </div>

      {/* Message */}
      {message && (
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
            {message}
          </p>
        </div>
      )}

      {/* Selections List */}
      <Card>
        {selections.length ? (
          <div className="space-y-3">
            {selections.map((selection, index) => (
              <div
                key={selection.match_id}
                className={cn(
                  "flex flex-col sm:flex-row sm:items-center justify-between gap-4",
                  "p-4 rounded-xl border border-white/[0.05] bg-white/[0.02]",
                  "transition-all duration-200 hover:border-white/[0.08]",
                  index !== selections.length - 1 && "mb-3"
                )}
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-sm font-semibold text-foreground-primary">
                      {selection.home_team}
                    </span>
                    <span className="text-xs text-foreground-muted">vs</span>
                    <span className="text-sm font-semibold text-foreground-primary">
                      {selection.away_team}
                    </span>
                  </div>
                  <div className="flex flex-wrap items-center gap-2 text-xs">
                    <Badge variant="accent" size="sm">
                      {selection.market_type}
                    </Badge>
                    <span className="text-foreground-muted">|</span>
                    <span className="text-foreground-tertiary">
                      Oran: <span className="font-semibold text-foreground-primary">{selection.odd.toFixed(2)}</span>
                    </span>
                    <span className="text-foreground-muted">|</span>
                    <span className={cn(
                      "font-medium",
                      selection.ev_percentage >= 0 ? "text-success" : "text-error"
                    )}>
                      EV: {selection.ev_percentage >= 0 ? "+" : ""}{selection.ev_percentage.toFixed(1)}%
                    </span>
                  </div>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => handleRemove(selection.match_id)}
                  className="text-error hover:text-error hover:bg-error/10 border-error/30 flex-shrink-0"
                >
                  <svg className="w-4 h-4 mr-1.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                  </svg>
                  Kaldır
                </Button>
              </div>
            ))}
          </div>
        ) : (
          <EmptyState onClear={() => window.location.href = "/dashboard"} />
        )}
      </Card>

      {/* Summary Card */}
      {selections.length > 0 && (
        <Card variant="accent">
          <CardHeader>
            <div className="flex items-center gap-2">
              <svg className="w-5 h-5 text-accent" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 7h6m0 10v-3m-3 3h.01M9 17h.01M9 14h.01M12 14h.01M15 11h.01M12 11h.01M9 11h.01M7 21h10a2 2 0 002-2V5a2 2 0 00-2-2H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
              </svg>
              <CardTitle>Kupon Özeti</CardTitle>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="p-4 rounded-xl bg-white/[0.04] border border-white/[0.06]">
                <p className="text-xs text-foreground-tertiary mb-1">Toplam Oran</p>
                <p className="text-2xl font-bold text-foreground-primary">
                  {totalOdds.toFixed(3)}
                </p>
              </div>
              <div className="p-4 rounded-xl bg-white/[0.04] border border-white/[0.06]">
                <p className="text-xs text-foreground-tertiary mb-1">Tahmini Kazanç</p>
                <p className="text-2xl font-bold text-success">
                  ₺{potentialWin.toFixed(2)}
                </p>
                <p className="text-[10px] text-foreground-muted mt-1">100 TL bahis için</p>
              </div>
            </div>
            <div className="flex items-center justify-between text-xs text-foreground-tertiary">
              <span>Maç sayısı: <strong className="text-foreground-primary">{selections.length}</strong></span>
              <span>Ort. güven: <strong className="text-foreground-primary">
                {(selections.reduce((acc, s) => acc + s.confidence_score, 0) / selections.length).toFixed(1)}%
              </strong></span>
            </div>
          </CardContent>
          <CardFooter className="border-t border-white/[0.04]">
            <Button 
              onClick={handleSave} 
              disabled={saving || !selections.length}
              size="lg"
              className="w-full"
            >
              {saving ? (
                <>
                  <svg className="animate-spin -ml-1 mr-2 h-4 w-4" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                  </svg>
                  Kaydediliyor...
                </>
              ) : (
                <>
                  <svg className="w-4 h-4 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-3m-1 4l-3 3m0 0l-3-3m3 3V4" />
                  </svg>
                  Kuponu Kaydet
                </>
              )}
            </Button>
          </CardFooter>
        </Card>
      )}
    </section>
  );
}
