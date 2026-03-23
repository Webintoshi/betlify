"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { getTeams, type TeamComparisonMetaResponse, type TeamDirectoryItem } from "@/lib/api";
import { TR, repairDisplayText } from "@/lib/tr-text";

type ComparisonControlsProps = {
  meta: TeamComparisonMetaResponse;
  initialHomeTeamId?: string;
  initialAwayTeamId?: string;
  initialHomeTeamName?: string;
  initialAwayTeamName?: string;
  initialScope: string;
  initialDataWindow: number;
  initialRobot: string;
};

function t(value: string): string {
  return repairDisplayText(value);
}

function TeamOption({ item, onSelect }: { item: TeamDirectoryItem; onSelect: (item: TeamDirectoryItem) => void }) {
  return (
    <button
      type="button"
      onClick={() => onSelect(item)}
      className="flex w-full items-center justify-between gap-3 rounded-lg border border-card-border bg-background-secondary px-3 py-2 text-left transition-colors hover:border-accent/40 hover:text-accent"
    >
      <span className="min-w-0">
        <span className="block truncate text-sm font-bold text-foreground-primary">{repairDisplayText(item.name)}</span>
        <span className="mt-1 block truncate text-[11px] font-medium text-foreground-muted">
          {repairDisplayText(item.league)} • {repairDisplayText(item.country)}
        </span>
      </span>
      <span className="text-[10px] font-black uppercase tracking-wide text-accent">ID</span>
    </button>
  );
}

export function ComparisonControls({
  meta,
  initialHomeTeamId,
  initialAwayTeamId,
  initialHomeTeamName,
  initialAwayTeamName,
  initialScope,
  initialDataWindow,
  initialRobot,
}: ComparisonControlsProps) {
  const router = useRouter();
  const [homeTeamId, setHomeTeamId] = useState(initialHomeTeamId ?? "");
  const [awayTeamId, setAwayTeamId] = useState(initialAwayTeamId ?? "");
  const [homeQuery, setHomeQuery] = useState(initialHomeTeamName ?? "");
  const [awayQuery, setAwayQuery] = useState(initialAwayTeamName ?? "");
  const [scope, setScope] = useState(initialScope);
  const [dataWindow, setDataWindow] = useState(String(initialDataWindow));
  const [robot, setRobot] = useState(initialRobot);
  const [homeResults, setHomeResults] = useState<TeamDirectoryItem[]>([]);
  const [awayResults, setAwayResults] = useState<TeamDirectoryItem[]>([]);
  const [homeSearching, setHomeSearching] = useState(false);
  const [awaySearching, setAwaySearching] = useState(false);

  useEffect(() => {
    setHomeTeamId(initialHomeTeamId ?? "");
    setAwayTeamId(initialAwayTeamId ?? "");
    setHomeQuery(initialHomeTeamName ?? "");
    setAwayQuery(initialAwayTeamName ?? "");
    setScope(initialScope);
    setDataWindow(String(initialDataWindow));
    setRobot(initialRobot);
  }, [initialAwayTeamId, initialAwayTeamName, initialDataWindow, initialHomeTeamId, initialHomeTeamName, initialRobot, initialScope]);

  useEffect(() => {
    const handle = window.setTimeout(async () => {
      const query = homeQuery.trim();
      if (query.length < 2 || homeTeamId) {
        setHomeResults([]);
        return;
      }
      setHomeSearching(true);
      try {
        const response = await getTeams({ q: query, limit: 8 });
        setHomeResults(response.items ?? []);
      } catch {
        setHomeResults([]);
      } finally {
        setHomeSearching(false);
      }
    }, 250);
    return () => window.clearTimeout(handle);
  }, [homeQuery, homeTeamId]);

  useEffect(() => {
    const handle = window.setTimeout(async () => {
      const query = awayQuery.trim();
      if (query.length < 2 || awayTeamId) {
        setAwayResults([]);
        return;
      }
      setAwaySearching(true);
      try {
        const response = await getTeams({ q: query, limit: 8 });
        setAwayResults(response.items ?? []);
      } catch {
        setAwayResults([]);
      } finally {
        setAwaySearching(false);
      }
    }, 250);
    return () => window.clearTimeout(handle);
  }, [awayQuery, awayTeamId]);

  const sameTeam = Boolean(homeTeamId && awayTeamId && homeTeamId === awayTeamId);
  const canSubmit = Boolean(homeTeamId && awayTeamId && !sameTeam);
  const featuredTeams = useMemo(() => meta.featured_teams ?? [], [meta.featured_teams]);

  function handleSelectHome(item: TeamDirectoryItem) {
    setHomeTeamId(item.id);
    setHomeQuery(repairDisplayText(item.name));
    setHomeResults([]);
  }

  function handleSelectAway(item: TeamDirectoryItem) {
    setAwayTeamId(item.id);
    setAwayQuery(repairDisplayText(item.name));
    setAwayResults([]);
  }

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSubmit) {
      return;
    }
    const search = new URLSearchParams();
    search.set("home_team_id", homeTeamId);
    search.set("away_team_id", awayTeamId);
    search.set("scope", scope || meta.default_scope);
    search.set("data_window", dataWindow || String(meta.default_data_window));
    search.set("robot", robot || meta.default_robot);
    router.push(`/takim-versus?${search.toString()}`);
  }

  return (
    <form onSubmit={handleSubmit} className="grid gap-6 rounded-2xl border border-card-border bg-card px-5 py-5 shadow-card lg:grid-cols-2">
      <div className="space-y-3">
        <label className="text-xs font-black uppercase tracking-wide text-foreground-muted">{t(TR.homeTeam)}</label>
        <div className="relative">
          <input
            value={homeQuery}
            onChange={(event) => {
              setHomeQuery(event.target.value);
              setHomeTeamId("");
            }}
            placeholder={t(TR.selectTeamPlaceholder)}
            className="w-full rounded-xl border border-card-border bg-background-secondary px-4 py-3 text-sm font-bold text-foreground-primary outline-none transition-colors focus:border-accent"
          />
          {homeSearching && <span className="absolute right-3 top-3 text-[11px] font-bold text-foreground-muted">...</span>}
        </div>
        {!homeTeamId && homeResults.length > 0 && (
          <div className="grid gap-2 rounded-xl border border-card-border bg-card-hover p-3">
            <p className="text-[11px] font-black uppercase tracking-wide text-foreground-muted">{t(TR.searchResults)}</p>
            {homeResults.map((item) => (
              <TeamOption key={item.id} item={item} onSelect={handleSelectHome} />
            ))}
          </div>
        )}
        {!homeTeamId && homeQuery.trim().length < 2 && featuredTeams.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {featuredTeams.slice(0, 6).map((item) => (
              <button
                key={`home-${item.id}`}
                type="button"
                onClick={() => handleSelectHome(item as TeamDirectoryItem)}
                className="rounded-md border border-card-border bg-background-secondary px-3 py-2 text-xs font-bold text-foreground-muted transition-colors hover:border-accent/40 hover:text-accent"
              >
                {repairDisplayText(item.name)}
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="space-y-3">
        <label className="text-xs font-black uppercase tracking-wide text-foreground-muted">{t(TR.awayTeam)}</label>
        <div className="relative">
          <input
            value={awayQuery}
            onChange={(event) => {
              setAwayQuery(event.target.value);
              setAwayTeamId("");
            }}
            placeholder={t(TR.selectTeamPlaceholder)}
            className="w-full rounded-xl border border-card-border bg-background-secondary px-4 py-3 text-sm font-bold text-foreground-primary outline-none transition-colors focus:border-accent"
          />
          {awaySearching && <span className="absolute right-3 top-3 text-[11px] font-bold text-foreground-muted">...</span>}
        </div>
        {!awayTeamId && awayResults.length > 0 && (
          <div className="grid gap-2 rounded-xl border border-card-border bg-card-hover p-3">
            <p className="text-[11px] font-black uppercase tracking-wide text-foreground-muted">{t(TR.searchResults)}</p>
            {awayResults.map((item) => (
              <TeamOption key={item.id} item={item} onSelect={handleSelectAway} />
            ))}
          </div>
        )}
        {!awayTeamId && awayQuery.trim().length < 2 && featuredTeams.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {featuredTeams.slice(6, 12).map((item) => (
              <button
                key={`away-${item.id}`}
                type="button"
                onClick={() => handleSelectAway(item as TeamDirectoryItem)}
                className="rounded-md border border-card-border bg-background-secondary px-3 py-2 text-xs font-bold text-foreground-muted transition-colors hover:border-accent/40 hover:text-accent"
              >
                {repairDisplayText(item.name)}
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="grid gap-3 sm:grid-cols-3 lg:col-span-2">
        <div className="space-y-2">
          <label className="text-xs font-black uppercase tracking-wide text-foreground-muted">{t(TR.comparisonScope)}</label>
          <select value={scope} onChange={(event) => setScope(event.target.value)} className="w-full rounded-xl border border-card-border bg-background-secondary px-4 py-3 text-sm font-bold text-foreground-primary outline-none transition-colors focus:border-accent">
            {meta.supported_scopes.map((item) => (
              <option key={item} value={item}>{item}</option>
            ))}
          </select>
        </div>
        <div className="space-y-2">
          <label className="text-xs font-black uppercase tracking-wide text-foreground-muted">{t(TR.comparisonWindow)}</label>
          <select value={dataWindow} onChange={(event) => setDataWindow(event.target.value)} className="w-full rounded-xl border border-card-border bg-background-secondary px-4 py-3 text-sm font-bold text-foreground-primary outline-none transition-colors focus:border-accent">
            {meta.supported_windows.map((item) => (
              <option key={item} value={String(item)}>{item} maç</option>
            ))}
          </select>
        </div>
        <div className="space-y-2">
          <label className="text-xs font-black uppercase tracking-wide text-foreground-muted">{t(TR.comparisonRobot)}</label>
          <select value={robot} onChange={(event) => setRobot(event.target.value)} className="w-full rounded-xl border border-card-border bg-background-secondary px-4 py-3 text-sm font-bold text-foreground-primary outline-none transition-colors focus:border-accent">
            {meta.supported_robots.map((item) => (
              <option key={item} value={item}>{item.toUpperCase()}</option>
            ))}
          </select>
        </div>
      </div>

      <div className="flex flex-col gap-3 lg:col-span-2 lg:flex-row lg:items-center lg:justify-between">
        <div className="text-sm font-bold text-error">{sameTeam ? t(TR.sameTeamError) : ""}</div>
        <button
          type="submit"
          disabled={!canSubmit}
          className="inline-flex items-center justify-center rounded-xl border border-accent bg-accent px-5 py-3 text-sm font-black uppercase tracking-wide text-white transition-opacity disabled:cursor-not-allowed disabled:opacity-40"
        >
          {t(TR.compareTeams)}
        </button>
      </div>
    </form>
  );
}
