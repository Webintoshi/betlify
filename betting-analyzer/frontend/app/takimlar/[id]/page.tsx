import Link from "next/link";
import { notFound } from "next/navigation";
import { Badge } from "@/components/ui/badge";
import { Card, CardDescription, CardTitle } from "@/components/ui/card";
import { getTeam, getTeamOverview, type TeamOverviewMatch, type TeamOverviewStatGroup, type TeamOverviewTournament } from "@/lib/api";
import { TR, repairDisplayText } from "@/lib/tr-text";

type TeamDetailPageProps = {
  params: Promise<{
    id: string;
  }>;
};

type TeamBase = {
  id: string;
  name: string;
  league: string;
  country: string;
  coach_name?: string | null;
  sofascore_id?: number | null;
  profile_sync_status?: string | null;
  profile_last_fetched_at?: string | null;
  team_data_sync_status?: string | null;
  team_data_last_fetched_at?: string | null;
};

function normalizeValue(value?: string | null): string {
  return String(value ?? "").trim();
}

function t(value: string): string {
  return repairDisplayText(value);
}

function formatDate(value?: string | null): string {
  const raw = normalizeValue(value);
  if (!raw) {
    return t(TR.notYet);
  }

  const parsed = new Date(raw);
  if (Number.isNaN(parsed.getTime())) {
    return raw;
  }

  return new Intl.DateTimeFormat("tr-TR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit"
  }).format(parsed);
}

function formatNumber(value: string | number | boolean | null | undefined): string {
  if (value === null || typeof value === "undefined" || value === "") {
    return "-";
  }

  if (typeof value === "boolean") {
    return value ? "Evet" : "Hayır";
  }

  if (typeof value === "number") {
    if (Number.isInteger(value)) {
      return new Intl.NumberFormat("tr-TR").format(value);
    }
    return new Intl.NumberFormat("tr-TR", { maximumFractionDigits: 3 }).format(value);
  }

  return repairDisplayText(value);
}

function TeamLogo({ teamId, teamName }: { teamId: string; teamName: string }) {
  return (
    <div className="flex h-24 w-24 items-center justify-center rounded-2xl border border-card-border bg-background-secondary p-3 shadow-card">
      <img
        src={`/api/backend/teams/${teamId}/logo`}
        alt={`${teamName} logosu`}
        className="h-full w-full object-contain"
      />
    </div>
  );
}

function getStatusView(status: string) {
  if (status === "ready") {
    return { label: t(TR.statusReady), variant: "success" as const };
  }
  if (status === "stale") {
    return { label: t(TR.statusStale), variant: "warning" as const };
  }
  return { label: t(TR.statusPending), variant: "neutral" as const };
}

function MatchResultBadge({ result }: { result?: string }) {
  const normalized = normalizeValue(result).toUpperCase();
  const variant =
    normalized === "W" ? "success" : normalized === "D" ? "warning" : normalized === "L" ? "error" : "neutral";

  return (
    <Badge variant={variant} size="sm">
      {normalized || "-"}
    </Badge>
  );
}

function LastFiveMatches({ matches }: { matches: TeamOverviewMatch[] }) {
  if (!matches.length) {
    return (
      <div className="rounded-lg border border-card-border bg-background-secondary px-4 py-6 text-sm font-bold text-foreground-muted">
        {t(TR.noOverviewData)}
      </div>
    );
  }

  return (
    <div className="grid gap-3">
      {matches.map((match, index) => {
        const homeTeam = repairDisplayText(match.home_team_name) || t(TR.unknown);
        const awayTeam = repairDisplayText(match.away_team_name) || t(TR.unknown);
        const leagueName = repairDisplayText(match.league) || t(TR.unknownLeague);
        const dateLabel = formatDate(match.date);
        const homeGoals = typeof match.home_goals === "number" ? match.home_goals : "-";
        const awayGoals = typeof match.away_goals === "number" ? match.away_goals : "-";

        return (
          <div
            key={`${match.event_id ?? "match"}-${index}`}
            className="grid gap-3 rounded-lg border border-card-border bg-background-secondary px-4 py-3 lg:grid-cols-[auto_1fr_auto]"
          >
            <div className="space-y-2">
              <MatchResultBadge result={match.result} />
              <p className="text-[11px] font-black uppercase tracking-wide text-foreground-muted">
                {match.is_home ? t(TR.home) : t(TR.away)}
              </p>
            </div>

            <div className="min-w-0">
              <p className="text-xs font-black uppercase tracking-wide text-accent">{leagueName}</p>
              <p className="mt-1 text-sm font-bold text-foreground-primary">
                {homeTeam} <span className="text-foreground-muted">{t(TR.versus)}</span> {awayTeam}
              </p>
              <p className="mt-1 text-xs font-medium text-foreground-muted">{dateLabel}</p>
            </div>

            <div className="flex items-center justify-end text-lg font-black text-foreground-primary">
              {homeGoals} - {awayGoals}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function FormOverview({ tournament }: { tournament: TeamOverviewTournament }) {
  const form = tournament.form_last_ten;
  const results = Array.isArray(form.results) ? form.results : [];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2">
        {results.length ? (
          results.map((result, index) => (
            <MatchResultBadge key={`${result}-${index}`} result={result} />
          ))
        ) : (
          <Badge variant="neutral" size="sm">
            -
          </Badge>
        )}
      </div>

      <div className="grid gap-3 sm:grid-cols-5">
        <div className="rounded-lg border border-card-border bg-background-secondary px-3 py-3">
          <p className="text-[11px] font-black uppercase tracking-wide text-foreground-muted">{t(TR.wins)}</p>
          <p className="mt-2 text-lg font-black text-foreground-primary">{formatNumber(form.wins)}</p>
        </div>
        <div className="rounded-lg border border-card-border bg-background-secondary px-3 py-3">
          <p className="text-[11px] font-black uppercase tracking-wide text-foreground-muted">{t(TR.draws)}</p>
          <p className="mt-2 text-lg font-black text-foreground-primary">{formatNumber(form.draws)}</p>
        </div>
        <div className="rounded-lg border border-card-border bg-background-secondary px-3 py-3">
          <p className="text-[11px] font-black uppercase tracking-wide text-foreground-muted">{t(TR.losses)}</p>
          <p className="mt-2 text-lg font-black text-foreground-primary">{formatNumber(form.losses)}</p>
        </div>
        <div className="rounded-lg border border-card-border bg-background-secondary px-3 py-3">
          <p className="text-[11px] font-black uppercase tracking-wide text-foreground-muted">{t(TR.points)}</p>
          <p className="mt-2 text-lg font-black text-foreground-primary">{formatNumber(form.points)}</p>
        </div>
        <div className="rounded-lg border border-card-border bg-background-secondary px-3 py-3">
          <p className="text-[11px] font-black uppercase tracking-wide text-foreground-muted">{t(TR.formScore)}</p>
          <p className="mt-2 text-lg font-black text-foreground-primary">
            {typeof form.score_pct === "number" ? `${Math.round(form.score_pct * 100)}%` : "-"}
          </p>
        </div>
      </div>
    </div>
  );
}

function StatsGrid({ title, group }: { title: string; group: TeamOverviewStatGroup }) {
  const items = Array.isArray(group.items) ? group.items : [];

  return (
    <Card className="space-y-4">
      <div className="border-b border-card-border pb-4">
        <CardTitle>{title}</CardTitle>
      </div>

      {items.length ? (
        <div className="grid gap-3 md:grid-cols-2">
          {items.map((item) => (
            <div key={item.key} className="rounded-lg border border-card-border bg-background-secondary px-4 py-3">
              <p className="text-[11px] font-black uppercase tracking-wide text-foreground-muted">
                {repairDisplayText(item.label) || item.key}
              </p>
              <p className="mt-2 text-sm font-bold text-foreground-primary">{formatNumber(item.value)}</p>
            </div>
          ))}
        </div>
      ) : (
        <div className="rounded-lg border border-card-border bg-background-secondary px-4 py-6 text-sm font-bold text-foreground-muted">
          {t(TR.noStatsInCategory)}
        </div>
      )}
    </Card>
  );
}

function TournamentSection({ tournament }: { tournament: TeamOverviewTournament }) {
  const tournamentName = repairDisplayText(tournament.tournament_name) || t(TR.unknownLeague);
  const seasonName = repairDisplayText(tournament.season_name) || String(tournament.season_id);

  return (
    <Card className="space-y-6">
      <div className="flex flex-col gap-3 border-b border-card-border pb-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <CardTitle>{tournamentName}</CardTitle>
          <CardDescription className="mt-2 normal-case tracking-normal">
            {seasonName}
          </CardDescription>
        </div>
        <Badge variant="accent" size="sm">
          {formatDate(tournament.updated_at)}
        </Badge>
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
        <div className="space-y-4">
          <div className="border-b border-card-border pb-3">
            <h3 className="text-sm font-black uppercase tracking-wide text-foreground-primary">{t(TR.lastFiveMatches)}</h3>
          </div>
          <LastFiveMatches matches={tournament.last_five_matches} />
        </div>

        <div className="space-y-4">
          <div className="border-b border-card-border pb-3">
            <h3 className="text-sm font-black uppercase tracking-wide text-foreground-primary">{t(TR.formLastTen)}</h3>
          </div>
          <FormOverview tournament={tournament} />
        </div>
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <StatsGrid title={t(TR.summaryStats)} group={tournament.summary_stats} />
        <StatsGrid title={t(TR.attackStats)} group={tournament.attack_stats} />
        <StatsGrid title={t(TR.passingStats)} group={tournament.passing_stats} />
        <StatsGrid title={t(TR.defendingStats)} group={tournament.defending_stats} />
      </div>

      <StatsGrid title={t(TR.otherStats)} group={tournament.other_stats} />
    </Card>
  );
}

export default async function TeamDetailPage({ params }: TeamDetailPageProps) {
  const { id } = await params;

  const [teamResult, overviewResult] = await Promise.allSettled([getTeam(id), getTeamOverview(id)]);

  if (teamResult.status === "rejected" && overviewResult.status === "rejected") {
    notFound();
  }

  const teamSource =
    overviewResult.status === "fulfilled" ? overviewResult.value.team : teamResult.status === "fulfilled" ? teamResult.value.team : null;

  if (!teamSource) {
    notFound();
  }

  const team = teamSource as TeamBase;
  const tournaments =
    overviewResult.status === "fulfilled" && Array.isArray(overviewResult.value.tournaments)
      ? overviewResult.value.tournaments
      : [];

  const teamName = repairDisplayText(team.name);
  const coachName = repairDisplayText(team.coach_name) || t(TR.unknown);
  const leagueName = repairDisplayText(team.league) || t(TR.unknownLeague);
  const countryName = repairDisplayText(team.country) || t(TR.unknown);
  const profileStatus = getStatusView(normalizeValue(team.profile_sync_status));
  const overviewStatus = getStatusView(normalizeValue(team.team_data_sync_status));

  return (
    <section className="space-y-8 animate-fade-in">
      <div className="flex flex-col gap-4 border-b-2 border-card-border pb-6 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex items-center gap-5">
          <TeamLogo teamId={team.id} teamName={teamName} />
          <div>
            <div className="mb-3 flex flex-wrap items-center gap-3">
              <Badge variant="accent" size="sm">
                {t(TR.teamProfile)}
              </Badge>
              <Badge variant={profileStatus.variant} size="sm">
                {profileStatus.label}
              </Badge>
              <Badge variant={overviewStatus.variant} size="sm">
                {t(TR.teamOverview)}: {overviewStatus.label}
              </Badge>
            </div>
            <h1 className="text-display-sm text-foreground-primary uppercase tracking-tight">{teamName}</h1>
            <p className="mt-2 text-sm font-bold uppercase tracking-wide text-foreground-muted">
              {leagueName} - {countryName}
            </p>
          </div>
        </div>

        <Link
          href="/takimler"
          className="inline-flex items-center justify-center rounded-lg border border-card-border px-4 py-3 text-xs font-black uppercase tracking-wide text-foreground-secondary transition-colors duration-150 hover:border-accent hover:text-accent"
        >
          {t(TR.backToTeams)}
        </Link>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1.15fr_0.85fr]">
        <Card className="space-y-5">
          <div className="border-b border-card-border pb-4">
            <CardTitle>{t(TR.genericInfo)}</CardTitle>
            <CardDescription className="mt-2 normal-case tracking-normal">
              {t(TR.genericInfoBody)}
            </CardDescription>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <div className="rounded-lg border border-card-border bg-background-secondary px-4 py-3">
              <p className="text-xs font-black uppercase tracking-wide text-foreground-muted">{t(TR.team)}</p>
              <p className="mt-2 text-sm font-bold text-foreground-primary">{teamName}</p>
            </div>
            <div className="rounded-lg border border-card-border bg-background-secondary px-4 py-3">
              <p className="text-xs font-black uppercase tracking-wide text-foreground-muted">{t(TR.league)}</p>
              <p className="mt-2 text-sm font-bold text-foreground-primary">{leagueName}</p>
            </div>
            <div className="rounded-lg border border-card-border bg-background-secondary px-4 py-3">
              <p className="text-xs font-black uppercase tracking-wide text-foreground-muted">{t(TR.country)}</p>
              <p className="mt-2 text-sm font-bold text-foreground-primary">{countryName}</p>
            </div>
            <div className="rounded-lg border border-card-border bg-background-secondary px-4 py-3">
              <p className="text-xs font-black uppercase tracking-wide text-foreground-muted">{t(TR.coach)}</p>
              <p className="mt-2 text-sm font-bold text-foreground-primary">{coachName}</p>
            </div>
          </div>
        </Card>

        <Card className="space-y-5">
          <div className="border-b border-card-border pb-4">
            <CardTitle>{t(TR.systemRecord)}</CardTitle>
            <CardDescription className="mt-2 normal-case tracking-normal">
              {t(TR.systemRecordBody)}
            </CardDescription>
          </div>

          <div className="grid gap-4">
            <div className="rounded-lg border border-card-border bg-background-secondary px-4 py-3">
              <p className="text-xs font-black uppercase tracking-wide text-foreground-muted">{t(TR.sofaScoreId)}</p>
              <p className="mt-2 text-sm font-bold text-foreground-primary">{team.sofascore_id ?? "-"}</p>
            </div>
            <div className="rounded-lg border border-card-border bg-background-secondary px-4 py-3">
              <p className="text-xs font-black uppercase tracking-wide text-foreground-muted">{t(TR.status)}</p>
              <p className="mt-2 text-sm font-bold text-foreground-primary">{profileStatus.label}</p>
            </div>
            <div className="rounded-lg border border-card-border bg-background-secondary px-4 py-3">
              <p className="text-xs font-black uppercase tracking-wide text-foreground-muted">{t(TR.lastSynced)}</p>
              <p className="mt-2 text-sm font-bold text-foreground-primary">{formatDate(team.profile_last_fetched_at)}</p>
            </div>
            <div className="rounded-lg border border-card-border bg-background-secondary px-4 py-3">
              <p className="text-xs font-black uppercase tracking-wide text-foreground-muted">{t(TR.overviewUpdatedAt)}</p>
              <p className="mt-2 text-sm font-bold text-foreground-primary">{formatDate(team.team_data_last_fetched_at)}</p>
            </div>
            <div className="rounded-lg border border-card-border bg-background-secondary px-4 py-3">
              <p className="text-xs font-black uppercase tracking-wide text-foreground-muted">{t(TR.activeTournaments)}</p>
              <p className="mt-2 text-sm font-bold text-foreground-primary">{formatNumber(tournaments.length)}</p>
            </div>
          </div>
        </Card>
      </div>

      <Card className="space-y-5">
        <div className="border-b border-card-border pb-4">
          <CardTitle>{t(TR.teamOverview)}</CardTitle>
          <CardDescription className="mt-2 normal-case tracking-normal">
            {t(TR.teamOverviewBody)}
          </CardDescription>
        </div>

        {tournaments.length ? (
          <div className="space-y-6">
            {tournaments.map((tournament) => (
              <TournamentSection
                key={`${tournament.tournament_id}-${tournament.season_id}`}
                tournament={tournament}
              />
            ))}
          </div>
        ) : (
          <div className="rounded-lg border border-card-border bg-background-secondary px-4 py-6 text-sm font-bold text-foreground-muted">
            {t(TR.noOverviewData)}
          </div>
        )}
      </Card>
    </section>
  );
}
