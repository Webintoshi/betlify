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

function getConfidenceVariant(confidence: number): "error" | "warning" | "success" {
  if (confidence < 60) return "error";
  if (confidence < 75) return "warning";
  return "success";
}

function getConfidenceLabel(confidence: number): string {
  if (confidence < 60) return "Düşük";
  if (confidence < 75) return "Orta";
  return "Yüksek";
}

export default function MatchCard({ match, isSelected, onAdd }: MatchCardProps) {
  const confidence = Math.max(0, Math.min(100, match.confidence_score));
  const weak = confidence < 60;
  const strong = confidence > 75;
  const confidenceVariant = getConfidenceVariant(confidence);

  return (
    <Card
      hover={!weak}
      className={cn(
        "relative overflow-hidden transition-all duration-500",
        weak && "opacity-60",
        strong && "border-success/40 shadow-success"
      )}
    >
      {/* Background gradient for strong matches */}
      {strong && (
        <div className="absolute inset-0 bg-gradient-to-br from-success/10 via-transparent to-transparent pointer-events-none" />
      )}

      {/* Content */}
      <div className="relative space-y-5">
        {/* Header */}
        <div className="flex items-start justify-between gap-4">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-2">
              <span className="text-lg">⚽</span>
              <p className="text-xs font-semibold uppercase tracking-wider text-sky-400 truncate">
                {match.league}
              </p>
            </div>
            <div className="flex items-center gap-2 text-xs text-slate-400">
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <span>{formatTime(match.match_date)}</span>
            </div>
          </div>
          <Badge 
            variant={match.recommended ? "success" : "neutral"}
            size="md"
            dot
          >
            {match.recommended ? "Önerilir" : "Önerilmez"}
          </Badge>
        </div>

        {/* Teams */}
        <div className="text-center py-2">
          <div className="flex items-center justify-center gap-3">
            <span className="text-base font-bold text-foreground-primary text-right flex-1 truncate">
              {match.home_team}
            </span>
            <div className="flex items-center justify-center w-10 h-10 rounded-full bg-accent/20 border border-accent/30">
              <span className="text-xs font-bold text-accent">VS</span>
            </div>
            <span className="text-base font-bold text-foreground-primary text-left flex-1 truncate">
              {match.away_team}
            </span>
          </div>
        </div>

        {/* Analysis Box */}
        <div className="rounded-xl border border-sky-500/10 bg-sky-500/5 p-4 space-y-3">
          {/* Market Type */}
          <div className="flex items-center justify-between">
            <span className="text-sm text-slate-400">Öneri</span>
            <span className="text-sm font-bold text-accent">
              {match.market_type}
            </span>
          </div>

          {/* EV Value */}
          <div className="flex items-center justify-between">
            <span className="text-sm text-slate-400">EV Değeri</span>
            <span className={cn(
              "text-sm font-bold",
              match.ev_percentage >= 0 ? "text-success-bright" : "text-error-bright"
            )}>
              {evText(match.ev_percentage)}
            </span>
          </div>

          {/* Confidence */}
          <div className="pt-2 border-t border-sky-500/10">
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                <span className="text-xs text-slate-400">Güven Skoru</span>
                <Badge variant={confidenceVariant} size="sm">
                  {getConfidenceLabel(confidence)}
                </Badge>
              </div>
              <span className="text-sm font-bold text-foreground-primary">
                {toPercent(confidence, 0)}
              </span>
            </div>
            <Progress 
              value={confidence} 
              variant={confidenceVariant}
              size="md"
              animated
            />
          </div>
        </div>

        {/* Actions */}
        <div className="grid grid-cols-2 gap-3 pt-1">
          <Link href={`/matches/${match.match_id}`} className="w-full">
            <Button 
              variant="secondary" 
              size="md"
              className="w-full group"
            >
              <svg 
                className="w-4 h-4 mr-2 transition-transform group-hover:scale-110" 
                fill="none" 
                viewBox="0 0 24 24" 
                stroke="currentColor"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01" />
              </svg>
              Detay
            </Button>
          </Link>
          <Button 
            size="md"
            variant={isSelected ? "outline" : "default"}
            onClick={() => onAdd(match)}
            className={cn(
              "w-full transition-all duration-300",
              isSelected && "border-success text-success hover:bg-success/10"
            )}
          >
            {isSelected ? (
              <>
                <svg className="w-4 h-4 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
                Eklendi
              </>
            ) : (
              <>
                <svg 
                  className="w-4 h-4 mr-2" 
                  fill="none" 
                  viewBox="0 0 24 24" 
                  stroke="currentColor"
                >
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                </svg>
                Kupon
              </>
            )}
          </Button>
        </div>
      </div>
    </Card>
  );
}
