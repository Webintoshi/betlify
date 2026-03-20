"use client";

import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardTitle } from "@/components/ui/card";
import { createCoupon } from "@/lib/api";
import {
  calculateTotalOdds,
  clearCouponSelections,
  getCouponSelections,
  removeCouponSelection,
  type CouponSelection
} from "@/lib/coupon-store";

export default function CouponPage() {
  const [selections, setSelections] = useState<CouponSelection[]>([]);
  const [saving, setSaving] = useState<boolean>(false);
  const [message, setMessage] = useState<string>("");
  const totalOdds = useMemo(() => calculateTotalOdds(selections), [selections]);

  useEffect(() => {
    setSelections(getCouponSelections());
  }, []);

  const handleRemove = (matchId: string) => {
    setSelections(removeCouponSelection(matchId));
  };

  const handleClear = () => {
    clearCouponSelections();
    setSelections([]);
    setMessage("Kupon temizlendi.");
  };

  const handleSave = async () => {
    if (!selections.length) {
      setMessage("Kaydedilecek seçim yok.");
      return;
    }
    setSaving(true);
    setMessage("");
    try {
      const response = await createCoupon(selections);
      setMessage(`Kupon kaydedildi. Kod: ${response.coupon_id}`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Kupon kaydedilemedi.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="space-y-6">
      <div>
        <p className="text-xs uppercase tracking-[0.2em] text-zinc-500">Kupon</p>
        <h1 className="mt-1 text-3xl font-bold text-white">Betlify Kupon Oluştur</h1>
      </div>

      <Card className="space-y-4">
        {selections.length ? (
          <div className="space-y-3">
            {selections.map((selection) => (
              <div
                key={selection.match_id}
                className="flex flex-col gap-3 rounded-xl border border-white/5 bg-[#141420] p-3 sm:flex-row sm:items-center sm:justify-between"
              >
                <div>
                  <p className="font-medium text-white">
                    {selection.home_team} vs {selection.away_team}
                  </p>
                  <p className="mt-1 text-sm text-zinc-400">
                    {selection.market_type} | Oran: {selection.odd.toFixed(2)}
                  </p>
                </div>
                <Button variant="danger" onClick={() => handleRemove(selection.match_id)}>
                  Sil
                </Button>
              </div>
            ))}
          </div>
        ) : (
          <CardDescription>Kuponda henüz maç yok. Dashboard veya Maç Detay’dan seçim ekleyin.</CardDescription>
        )}
      </Card>

      <Card className="space-y-3">
        <CardTitle>Kupon Özeti</CardTitle>
        <div className="text-sm text-zinc-300">
          Toplam oran: <span className="text-xl font-bold text-white">{totalOdds.toFixed(3)}</span>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button onClick={handleSave} disabled={saving || !selections.length}>
            {saving ? "Kaydediliyor..." : "Kuponu Kaydet"}
          </Button>
          <Button variant="secondary" onClick={handleClear}>
            Temizle
          </Button>
        </div>
        {message ? <p className="text-sm text-zinc-400">{message}</p> : null}
      </Card>
    </section>
  );
}
