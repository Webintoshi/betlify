import Link from "next/link";
import { notFound } from "next/navigation";
import { Badge } from "@/components/ui/badge";
import { Card, CardDescription, CardTitle } from "@/components/ui/card";
import { getTeam } from "@/lib/api";
import { TR, repairDisplayText } from "@/lib/tr-text";

type TeamDetailPageProps = {
  params: Promise<{
    id: string;
  }>;
};

function normalizeValue(value?: string | null): string {
  return String(value ?? "").trim();
}

function t(value: string): string {
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

export default async function TeamDetailPage({ params }: TeamDetailPageProps) {
  const { id } = await params;

  let response;
  try {
    response = await getTeam(id);
  } catch {
    notFound();
  }

  const team = response.team;
  const teamName = repairDisplayText(team.name);
  const coachName = repairDisplayText(team.coach_name) || t(TR.unknown);
  const leagueName = repairDisplayText(team.league) || t(TR.unknownLeague);
  const countryName = repairDisplayText(team.country) || t(TR.unknown);
  const syncStatus = normalizeValue(team.profile_sync_status);
  const statusLabel =
    syncStatus === "ready"
      ? t(TR.statusReady)
      : syncStatus === "stale"
        ? t(TR.statusStale)
        : t(TR.statusPending);
  const badgeVariant = syncStatus === "ready" ? "success" : syncStatus === "stale" ? "warning" : "neutral";

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
              <Badge variant={badgeVariant} size="sm">
                {statusLabel}
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

      <div className="grid gap-6 lg:grid-cols-[1.2fr_0.8fr]">
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
              <p className="mt-2 text-sm font-bold text-foreground-primary">{statusLabel}</p>
            </div>
            <div className="rounded-lg border border-card-border bg-background-secondary px-4 py-3">
              <p className="text-xs font-black uppercase tracking-wide text-foreground-muted">{t(TR.lastSynced)}</p>
              <p className="mt-2 text-sm font-bold text-foreground-primary">{normalizeValue(team.profile_last_fetched_at) || t(TR.notYet)}</p>
            </div>
          </div>
        </Card>
      </div>
    </section>
  );
}
