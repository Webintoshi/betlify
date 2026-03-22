import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { Card, CardDescription, CardTitle } from "@/components/ui/card";
import { getTeams, type TeamDirectoryItem } from "@/lib/api";
import { cn } from "@/lib/utils";

type TeamsPageProps = {
  searchParams?: Promise<{
    league?: string;
    country?: string;
    q?: string;
    limit?: string;
  }>;
};

function normalizeValue(value?: string): string {
  return String(value ?? "").trim();
}

function buildLeagueOptions(items: TeamDirectoryItem[]): string[] {
  return Array.from(new Set(items.map((item) => normalizeValue(item.league)).filter(Boolean))).sort((a, b) =>
    a.localeCompare(b, "tr")
  );
}

function buildCountryOptions(items: TeamDirectoryItem[]): string[] {
  return Array.from(new Set(items.map((item) => normalizeValue(item.country)).filter(Boolean))).sort((a, b) =>
    a.localeCompare(b, "tr")
  );
}

function groupTeamsByLeague(items: TeamDirectoryItem[]): Array<[string, TeamDirectoryItem[]]> {
  const grouped = new Map<string, TeamDirectoryItem[]>();
  for (const item of items) {
    const leagueName = normalizeValue(item.league) || "Bilinmeyen Lig";
    const bucket = grouped.get(leagueName) ?? [];
    bucket.push(item);
    grouped.set(leagueName, bucket);
  }

  return Array.from(grouped.entries())
    .sort((left, right) => left[0].localeCompare(right[0], "tr"))
    .map(([league, teams]) => [
      league,
      [...teams].sort((left, right) => normalizeValue(left.name).localeCompare(normalizeValue(right.name), "tr"))
    ]);
}

function TeamLogo({ team }: { team: TeamDirectoryItem }) {
  const logoUrl = normalizeValue(team.logo_url || "");
  if (!logoUrl) {
    return (
      <div className="flex h-14 w-14 items-center justify-center rounded-xl border border-card-border bg-background-secondary text-sm font-black uppercase text-accent">
        {normalizeValue(team.name).slice(0, 2) || "TA"}
      </div>
    );
  }

  return (
    <div className="flex h-14 w-14 items-center justify-center rounded-xl border border-card-border bg-background-secondary p-2">
      <img
        src={logoUrl}
        alt={`${team.name} logosu`}
        className="h-full w-full object-contain"
        loading="lazy"
      />
    </div>
  );
}

function TeamCard({ team }: { team: TeamDirectoryItem }) {
  const profileUrl = normalizeValue(team.sofascore_team_url || "");
  const coachName = normalizeValue(team.coach_name || "");
  const syncStatus = normalizeValue(team.profile_sync_status || "");
  const badgeVariant =
    syncStatus === "ready" ? "success" : syncStatus === "stale" ? "warning" : "neutral";

  return (
    <Card hover className="flex h-full flex-col gap-4 p-4">
      <div className="flex items-start gap-4">
        <TeamLogo team={team} />

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <CardTitle className="text-base">{team.name}</CardTitle>
            <Badge variant={badgeVariant} size="sm">
              {syncStatus === "ready" ? "Hazir" : syncStatus === "stale" ? "Bayat" : "Bekliyor"}
            </Badge>
          </div>
          <CardDescription className="mt-1 uppercase tracking-wide">
            {team.country || "Bilinmiyor"}
          </CardDescription>
        </div>
      </div>

      <dl className="grid gap-3 text-xs">
        <div className="rounded-lg border border-card-border bg-background-secondary px-3 py-2">
          <dt className="font-black uppercase tracking-wide text-foreground-muted">Takim</dt>
          <dd className="mt-1 font-bold text-foreground-primary">{team.name}</dd>
        </div>
        <div className="rounded-lg border border-card-border bg-background-secondary px-3 py-2">
          <dt className="font-black uppercase tracking-wide text-foreground-muted">Ulkesi</dt>
          <dd className="mt-1 font-bold text-foreground-primary">{team.country || "Bilinmiyor"}</dd>
        </div>
        <div className="rounded-lg border border-card-border bg-background-secondary px-3 py-2">
          <dt className="font-black uppercase tracking-wide text-foreground-muted">Teknik Direktör</dt>
          <dd className="mt-1 font-bold text-foreground-primary">{coachName || "Bilinmiyor"}</dd>
        </div>
      </dl>

      <div className="mt-auto flex items-center justify-between gap-3 pt-2">
        <Badge variant="accent" size="sm">
          ID #{team.sofascore_id ?? "-"}
        </Badge>
        {profileUrl ? (
          <Link
            href={profileUrl}
            target="_blank"
            rel="noreferrer"
            className={cn(
              "inline-flex items-center gap-2 rounded-lg border border-accent px-3 py-2",
              "text-xs font-black uppercase tracking-wide text-accent transition-colors duration-150",
              "hover:bg-accent hover:text-white"
            )}
          >
            SofaScore Profili
          </Link>
        ) : (
          <span className="text-[11px] font-bold uppercase tracking-wide text-foreground-muted">
            Profil baglantisi yok
          </span>
        )}
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

  const teamsResponse = await getTeams({
    league: league || undefined,
    country: country || undefined,
    q: q || undefined,
    limit
  });

  const allTeamsResponse = await getTeams({ limit: 500 });
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
          <h1 className="text-display-sm text-foreground-primary uppercase tracking-tight">Takimlar</h1>
          <p className="mt-1 text-sm font-bold uppercase tracking-wide text-foreground-muted">
            Lig bazli takim dizini, logo, ulke ve teknik direktor profili
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <Badge variant="neutral" size="md">
            Toplam {teamsResponse.count} takim
          </Badge>
          {league ? (
            <Badge variant="success" size="md">
              Lig: {league}
            </Badge>
          ) : null}
          {country ? (
            <Badge variant="warning" size="md">
              Ulke: {country}
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
          <CardTitle>Takim Filtresi</CardTitle>
        </div>

        <form action="/takimler" className="grid gap-4 lg:grid-cols-4">
          <div className="space-y-2">
            <label className="text-xs font-black uppercase tracking-wide text-foreground-tertiary">Lig</label>
            <select
              name="league"
              defaultValue={league}
              className="w-full rounded-lg border-2 border-card-border bg-background-secondary px-4 py-3 text-sm font-bold uppercase tracking-wide text-foreground-primary focus:border-accent focus:outline-none"
            >
              <option value="">Tum Ligler</option>
              {leagueOptions.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </div>

          <div className="space-y-2">
            <label className="text-xs font-black uppercase tracking-wide text-foreground-tertiary">Ulke</label>
            <select
              name="country"
              defaultValue={country}
              className="w-full rounded-lg border-2 border-card-border bg-background-secondary px-4 py-3 text-sm font-bold uppercase tracking-wide text-foreground-primary focus:border-accent focus:outline-none"
            >
              <option value="">Tum Ulkeler</option>
              {countryOptions.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </div>

          <div className="space-y-2">
            <label className="text-xs font-black uppercase tracking-wide text-foreground-tertiary">Takim Ara</label>
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
                Filtreye uygun takim bulunamadi
              </p>
              <p className="mt-1 text-xs font-bold uppercase tracking-wide text-foreground-muted">
                Lig veya ulke filtresini gevsetip tekrar deneyin
              </p>
            </div>
          </div>
        </Card>
      ) : (
        <div className="space-y-8">
          {groupedTeams.map(([leagueName, teams]) => (
            <section key={leagueName} className="space-y-4">
              <div className="flex flex-wrap items-center gap-3 border-b border-card-border pb-3">
                <CardTitle className="text-base">{leagueName}</CardTitle>
                <Badge variant="neutral" size="sm">
                  {teams.length} takim
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
