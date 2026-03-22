import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { Card, CardDescription, CardTitle } from "@/components/ui/card";
import { getTeams, type TeamDirectoryItem } from "@/lib/api";

type TeamsPageProps = {
  searchParams?: Promise<{
    league?: string;
    country?: string;
    q?: string;
    limit?: string;
  }>;
};

type LeagueOption = {
  value: string;
  label: string;
};

function normalizeValue(value?: string | null): string {
  return String(value ?? "").trim();
}

function repairMojibakeText(value?: string | null): string {
  const text = normalizeValue(value);
  if (!text) {
    return "";
  }
  if (!/[ÃÄÅ]/.test(text)) {
    return text;
  }
  try {
    const bytes = Uint8Array.from(Array.from(text), (character) => character.charCodeAt(0) & 0xff);
    const repaired = new TextDecoder("utf-8").decode(bytes).trim();
    return repaired || text;
  } catch {
    return text;
  }
}

function normalizeLeagueKey(value?: string): string {
  const compact = repairMojibakeText(value)
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-zA-Z0-9]+/g, "")
    .toLowerCase();
  const aliases: Record<string, string> = {
    trendyolsuperlig: "trendyolsuperlig",
    turkiyesuperlig: "trendyolsuperlig",
    superlig: "trendyolsuperlig",
    turkeysuperleague: "trendyolsuperlig",
    superleagueturkey: "trendyolsuperlig",
    trendyol1lig: "trendyol1lig",
    tff1lig: "trendyol1lig",
    "1lig": "trendyol1lig",
  };
  return aliases[compact] ?? compact;
}

const LEAGUE_PRIORITY_ORDER = [
  "trendyolsuperlig",
  "turkiyesuperlig",
  "superlig",
  "premierleague",
  "premierlig",
  "laliga",
  "seriea",
  "bundesliga",
  "ligue1",
  "uefachampionsleague",
  "sampiyonlarligi",
  "uefaeuropaleague",
  "avrupaligi",
  "uefaeuropaconferenceleague",
  "konferansligi",
  "championship",
  "eredivisie",
  "primeiraliga",
  "proleague",
  "scottishpremiership",
  "superleaguegreece",
  "tff1lig",
  "trendyol1lig",
  "1lig",
  "2bundesliga",
  "serieb",
  "ligue2",
  "brasileiraobetano",
  "mls",
  "saudiproleague",
  "j1league",
];

const LEAGUE_DISPLAY_LABELS: Record<string, string> = {
  trendyolsuperlig: "Trendyol S\u00fcper Lig",
  premierleague: "Premier Lig",
  premierlig: "Premier Lig",
  laliga: "La Liga",
  seriea: "Serie A",
  bundesliga: "Bundesliga",
  ligue1: "Ligue 1",
  uefachampionsleague: "\u015eampiyonlar Ligi",
  sampiyonlarligi: "\u015eampiyonlar Ligi",
  uefaeuropaleague: "Avrupa Ligi",
  avrupaligi: "Avrupa Ligi",
  uefaeuropaconferenceleague: "Konferans Ligi",
  konferansligi: "Konferans Ligi",
  championship: "Championship",
  eredivisie: "Eredivisie",
  primeiraliga: "Primeira Liga",
  proleague: "Bel\u00e7ika Pro League",
  scottishpremiership: "\u0130sko\u00e7ya Premiership",
  superleaguegreece: "Yunanistan S\u00fcper Ligi",
  trendyol1lig: "Trendyol 1. Lig",
  "2bundesliga": "2. Bundesliga",
  serieb: "Serie B",
  ligue2: "Ligue 2",
  brasileiraobetano: "Brezilya S\u00e9rie A",
  mls: "MLS",
  saudiproleague: "Suudi Pro Lig",
  j1league: "J1 League",
};

function leaguePriorityIndex(value?: string): number {
  const key = normalizeLeagueKey(value);
  const index = LEAGUE_PRIORITY_ORDER.indexOf(key);
  return index >= 0 ? index : Number.MAX_SAFE_INTEGER;
}

function getLeagueDisplayLabel(value?: string): string {
  const raw = repairMojibakeText(value);
  if (!raw) {
    return "Bilinmeyen Lig";
  }
  return LEAGUE_DISPLAY_LABELS[normalizeLeagueKey(raw)] ?? raw;
}

function compareLeagueNames(left: string, right: string): number {
  const leftPriority = leaguePriorityIndex(left);
  const rightPriority = leaguePriorityIndex(right);
  if (leftPriority !== rightPriority) {
    return leftPriority - rightPriority;
  }
  return getLeagueDisplayLabel(left).localeCompare(getLeagueDisplayLabel(right), "tr");
}

function buildLeagueOptions(items: TeamDirectoryItem[]): LeagueOption[] {
  const seen = new Set<string>();
  const options: LeagueOption[] = [];

  for (const item of items) {
    const raw = repairMojibakeText(item.league);
    if (!raw) {
      continue;
    }
    const key = normalizeLeagueKey(raw);
    if (!key || seen.has(key)) {
      continue;
    }
    seen.add(key);
    options.push({
      value: getLeagueDisplayLabel(raw),
      label: getLeagueDisplayLabel(raw),
    });
  }

  return options.sort((left, right) => compareLeagueNames(left.label, right.label));
}

function buildCountryOptions(items: TeamDirectoryItem[]): string[] {
  return Array.from(new Set(items.map((item) => repairMojibakeText(item.country)).filter(Boolean))).sort((a, b) =>
    a.localeCompare(b, "tr")
  );
}

function groupTeamsByLeague(items: TeamDirectoryItem[]): Array<[string, TeamDirectoryItem[]]> {
  const grouped = new Map<string, TeamDirectoryItem[]>();
  for (const item of items) {
    const leagueName = getLeagueDisplayLabel(item.league);
    const bucket = grouped.get(leagueName) ?? [];
    bucket.push(item);
    grouped.set(leagueName, bucket);
  }

  return Array.from(grouped.entries())
    .sort((left, right) => compareLeagueNames(left[0], right[0]))
    .map(([league, teams]) => [
      league,
      [...teams].sort((left, right) => repairMojibakeText(left.name).localeCompare(repairMojibakeText(right.name), "tr"))
    ]);
}

function TeamLogo({ team }: { team: TeamDirectoryItem }) {
  const logoUrl = team.id ? `/api/backend/teams/${team.id}/logo` : normalizeValue(team.logo_url || "");
  if (!logoUrl) {
    return (
      <div className="flex h-14 w-14 items-center justify-center rounded-xl border border-card-border bg-background-secondary text-sm font-black uppercase text-accent">
        {repairMojibakeText(team.name).slice(0, 2) || "TA"}
      </div>
    );
  }

  return (
    <div className="flex h-14 w-14 items-center justify-center rounded-xl border border-card-border bg-background-secondary p-2">
      <img
        src={logoUrl}
        alt={`${repairMojibakeText(team.name)} logosu`}
        className="h-full w-full object-contain"
        loading="lazy"
      />
    </div>
  );
}

function TeamCard({ team }: { team: TeamDirectoryItem }) {
  const coachName = repairMojibakeText(team.coach_name);
  const teamName = repairMojibakeText(team.name);
  const countryName = repairMojibakeText(team.country) || "Bilinmiyor";
  const syncStatus = normalizeValue(team.profile_sync_status || "");
  const badgeVariant =
    syncStatus === "ready" ? "success" : syncStatus === "stale" ? "warning" : "neutral";
  const statusLabel = syncStatus === "ready" ? "Haz\u0131r" : syncStatus === "stale" ? "G\u00fcncellenecek" : "Bekliyor";

  return (
    <Card hover className="flex h-full flex-col gap-4 p-4">
      <div className="flex items-start gap-4">
        <TeamLogo team={team} />

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <CardTitle className="text-base">{teamName}</CardTitle>
            <Badge variant={badgeVariant} size="sm">
              {statusLabel}
            </Badge>
          </div>
          <CardDescription className="mt-1 tracking-wide">{countryName}</CardDescription>
        </div>
      </div>

      <dl className="grid gap-3 text-xs">
        <div className="rounded-lg border border-card-border bg-background-secondary px-3 py-2">
          <dt className="font-black uppercase tracking-wide text-foreground-muted">Tak\u0131m</dt>
          <dd className="mt-1 font-bold text-foreground-primary">{teamName}</dd>
        </div>
        <div className="rounded-lg border border-card-border bg-background-secondary px-3 py-2">
          <dt className="font-black uppercase tracking-wide text-foreground-muted">\u00dclkesi</dt>
          <dd className="mt-1 font-bold text-foreground-primary">{countryName}</dd>
        </div>
        <div className="rounded-lg border border-card-border bg-background-secondary px-3 py-2">
          <dt className="font-black uppercase tracking-wide text-foreground-muted">Teknik Direkt\u00f6r</dt>
          <dd className="mt-1 font-bold text-foreground-primary">{coachName || "Bilinmiyor"}</dd>
        </div>
      </dl>

      <div className="mt-auto flex items-center justify-between gap-3 pt-2">
        <Badge variant="accent" size="sm">
          ID #{team.sofascore_id ?? "-"}
        </Badge>
        <Link
          href={`/takimler/${team.id}`}
          className="inline-flex items-center gap-2 rounded-lg border border-accent px-3 py-2 text-xs font-black uppercase tracking-wide text-accent transition-colors duration-150 hover:bg-accent hover:text-white"
        >
          Tak\u0131m Detay\u0131
        </Link>
      </div>
    </Card>
  );
}

export default async function TeamsPage({ searchParams }: TeamsPageProps) {
  const params = (await searchParams) ?? {};
  const league = normalizeValue(params.league);
  const country = normalizeValue(params.country);
  const q = normalizeValue(params.q);
  const limit = Math.max(1, Math.min(Number(params.limit) || 200, 500));

  let teamsResponse: { count: number; items: TeamDirectoryItem[] } = {
    count: 0,
    items: []
  };
  let allTeamsResponse: { count: number; items: TeamDirectoryItem[] } = {
    count: 0,
    items: []
  };
  let fetchError: string | null = null;

  try {
    [teamsResponse, allTeamsResponse] = await Promise.all([
      getTeams({
        league: league || undefined,
        country: country || undefined,
        q: q || undefined,
        limit
      }),
      getTeams({ limit: 6000 })
    ]);
  } catch (error) {
    fetchError = error instanceof Error ? error.message : "Tak\u0131m verisi al\u0131namad\u0131";
  }

  const leagueOptions = buildLeagueOptions(allTeamsResponse.items ?? []);
  const countryOptions = buildCountryOptions(allTeamsResponse.items ?? []);
  const groupedTeams = groupTeamsByLeague(teamsResponse.items ?? []);

  return (
    <section className="space-y-8 animate-fade-in">
      <div className="flex flex-col gap-4 border-b-2 border-card-border pb-6 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <div className="mb-2 flex items-center gap-3">
            <Badge variant="accent" size="sm">
              SofaScore Cache
            </Badge>
            <p className="text-xs font-black uppercase tracking-[0.3em] text-accent">Betlify</p>
          </div>
          <h1 className="text-display-sm text-foreground-primary uppercase tracking-tight">Tak\u0131mlar</h1>
          <p className="mt-1 text-sm font-bold uppercase tracking-wide text-foreground-muted">
            Lig bazl\u0131 tak\u0131m dizini, logo, \u00fclke ve teknik direkt\u00f6r profili
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <Badge variant="neutral" size="md">
            Toplam {teamsResponse.count} tak\u0131m
          </Badge>
          {league ? (
            <Badge variant="success" size="md">
              Lig: {league}
            </Badge>
          ) : null}
          {country ? (
            <Badge variant="warning" size="md">
              \u00dclke: {country}
            </Badge>
          ) : null}
        </div>
      </div>

      <Card>
        <div className="mb-5 flex items-center gap-3 border-b-2 border-card-border pb-4">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-accent text-white">
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2.586a1 1 0 01-.293.707l-6.414 6.414a1 1 0 00-.293.707V17l-4 4v-6.586a1 1 0 00-.293-.707L3.293 7.293A1 1 0 013 6.586V4z" />
            </svg>
          </div>
          <CardTitle>Tak\u0131m Filtresi</CardTitle>
        </div>

        <form action="/takimler" className="grid gap-4 lg:grid-cols-4">
          <div className="space-y-2">
            <label className="text-xs font-black uppercase tracking-wide text-foreground-tertiary">Lig</label>
            <select
              name="league"
              defaultValue={league}
              className="w-full rounded-lg border-2 border-card-border bg-background-secondary px-4 py-3 text-sm font-bold uppercase tracking-wide text-foreground-primary focus:border-accent focus:outline-none"
            >
              <option value="">T\u00fcm Ligler</option>
              {leagueOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>

          <div className="space-y-2">
            <label className="text-xs font-black uppercase tracking-wide text-foreground-tertiary">\u00dclke</label>
            <select
              name="country"
              defaultValue={country}
              className="w-full rounded-lg border-2 border-card-border bg-background-secondary px-4 py-3 text-sm font-bold uppercase tracking-wide text-foreground-primary focus:border-accent focus:outline-none"
            >
              <option value="">T\u00fcm \u00dclkeler</option>
              {countryOptions.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </div>

          <div className="space-y-2">
            <label className="text-xs font-black uppercase tracking-wide text-foreground-tertiary">Tak\u0131m Ara</label>
            <input
              type="text"
              name="q"
              defaultValue={q}
              placeholder="Galatasaray, Sunderland..."
              className="w-full rounded-lg border-2 border-card-border bg-background-secondary px-4 py-3 text-sm font-bold text-foreground-primary placeholder:text-foreground-muted focus:border-accent focus:outline-none"
            />
          </div>

          <div className="space-y-2">
            <label className="text-xs font-black uppercase tracking-wide text-foreground-tertiary">Limit</label>
            <div className="flex gap-2">
              <input
                type="number"
                name="limit"
                min={1}
                max={500}
                defaultValue={String(limit)}
                className="w-full rounded-lg border-2 border-card-border bg-background-secondary px-4 py-3 text-sm font-bold text-foreground-primary focus:border-accent focus:outline-none"
              />
              <button
                type="submit"
                className="rounded-lg border-2 border-accent bg-accent px-5 py-3 text-xs font-black uppercase tracking-wide text-white transition-colors duration-150 hover:bg-accent-secondary"
              >
                Getir
              </button>
            </div>
          </div>
        </form>
      </Card>

      {fetchError ? (
        <Card className="border-2 border-amber-500/30 bg-amber-500/5">
          <div className="flex items-start gap-3">
            <div className="mt-0.5 flex h-10 w-10 items-center justify-center rounded-lg bg-amber-500/15 text-amber-300">
              <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v3.75m0 3.75h.008v.008H12v-.008z" />
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.29 3.86l-7.5 13A1 1 0 003.65 18.5h16.7a1 1 0 00.86-1.64l-7.5-13a1 1 0 00-1.72 0z" />
              </svg>
            </div>
            <div className="min-w-0">
              <CardTitle className="text-sm">Tak\u0131m verisi \u015fu anda y\u00fcklenemedi</CardTitle>
              <CardDescription className="mt-1 normal-case tracking-normal">
                Backend ba\u011flant\u0131s\u0131 veya ortam de\u011fi\u015fkeni hatas\u0131 var. Ayr\u0131nt\u0131: {fetchError}
              </CardDescription>
            </div>
          </div>
        </Card>
      ) : null}

      {groupedTeams.length === 0 ? (
        <Card className="py-16 text-center">
          <div className="mx-auto flex max-w-md flex-col items-center gap-4">
            <div className="flex h-16 w-16 items-center justify-center rounded-lg bg-card-hover text-foreground-muted">
              <svg className="h-8 w-8" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.172 16.172a4 4 0 015.656 0M9 10h.01M15 10h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
            <div>
              <p className="text-sm font-black uppercase tracking-wide text-foreground-secondary">
                Filtreye uygun tak\u0131m bulunamad\u0131
              </p>
              <p className="mt-1 text-xs font-bold uppercase tracking-wide text-foreground-muted">
                Lig veya \u00fclke filtresini gev\u015fetip tekrar deneyin
              </p>
            </div>
          </div>
        </Card>
      ) : (
        <div className="space-y-8">
          {groupedTeams.map(([leagueName, teams]) => (
            <section key={leagueName} className="space-y-4">
              <div className="flex flex-wrap items-center gap-3 border-b border-card-border pb-3">
                <CardTitle className="text-base">{getLeagueDisplayLabel(leagueName)}</CardTitle>
                <Badge variant="neutral" size="sm">
                  {teams.length} tak\u0131m
                </Badge>
              </div>

              <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                {teams.map((team) => (
                  <TeamCard key={team.id} team={team} />
                ))}
              </div>
            </section>
          ))}
        </div>
      )}
    </section>
  );
}
