"use client";

import Link from "next/link";
import type { DashboardMatch } from "@/lib/api";
import { cn, formatTime, toPercent } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";

type MatchCardProps = {
  match: DashboardMatch;
  isSelected: boolean;
  onAdd: (match: DashboardMatch) => void;
};

function evText(ev: number): string {
  const sign = ev >= 0 ? "+" : "";
  return `${sign}${ev.toFixed(1)}%`;
}

export default function MatchCard({ match, isSelected, onAdd }: MatchCardProps) {
  const confidence = Math.max(0, Math.min(100, match.confidence_score));
  const weak = confidence < 60;
  const strong = confidence > 75;

  return (
    <Card
      className={cn(
        "space-y-4 transition",
        weak && "opacity-55 saturate-75",
        strong && "border-emerald-500/40 shadow-[0_0_0_1px_rgba(16,185,129,0.25)]"
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-wide text-zinc-400">🏆 {match.league}</p>
          <p className="mt-1 text-xs text-zinc-400">{formatTime(match.match_date)}</p>
        </div>
        <Badge variant={match.recommended ? "success" : "neutral"}>{match.recommended ? "Önerilir" : "Önerilmez"}</Badge>
      </div>

      <div className="text-center">
        <p className="text-lg font-semibold text-white">
          {match.home_team} <span className="mx-2 text-zinc-500">vs</span> {match.away_team}
        </p>
      </div>

      <div className="grid gap-1 rounded-xl border border-white/5 bg-[#141420] p-3 text-sm">
        <p className="text-zinc-300">
          Öneri: <span className="font-semibold text-white">{match.market_type}</span>
        </p>
        <p className="text-zinc-300">
          EV: <span className={cn("font-semibold", match.ev_percentage >= 0 ? "text-emerald-300" : "text-red-300")}>{evText(match.ev_percentage)}</span>
        </p>
        <div className="mt-1">
          <div className="mb-1 flex items-center justify-between text-xs text-zinc-400">
            <span>Güven</span>
            <span>{toPercent(confidence, 0)}</span>
          </div>
          <Progress value={confidence} barClassName={strong ? "bg-emerald-400" : "bg-[#6366f1]"} />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2">
        <Link href={`/matches/${match.match_id}`} className="w-full">
          <Button variant="secondary" className="w-full">
            Detay
          </Button>
        </Link>
        <Button className="w-full" variant={isSelected ? "ghost" : "default"} onClick={() => onAdd(match)}>
          {isSelected ? "Kuponda ✓" : "Kupona Ekle"}
        </Button>
      </div>
    </Card>
  );
}
