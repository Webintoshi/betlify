import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { Card, CardDescription, CardTitle } from "@/components/ui/card";
import {
  getTeamComparison,
  getTeamComparisonMeta,
  type TeamComparisonCard,
  type TeamComparisonResponse,
  type TeamComparisonRobotOutput,
} from "@/lib/api";
import { TR, repairDisplayText } from "@/lib/tr-text";
import { ComparisonControls } from "./ComparisonControls";

type TeamVersusPageProps = {
  searchParams?: Promise<{
    home_team_id?: string;
    away_team_id?: string;
    scope?: string;
    data_window?: string;
    robot?: string;
    refresh?: string;
  }>;
};

function t(value: string): string {
  return repairDisplayText(value);
}

function normalizeValue(value?: string | null): string {
  return String(value ?? "").trim();
}

function buildHref(params: Record<string, string | number | boolean | undefined>) {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (typeof value === "undefined" || value === "" || value === false) {
      return;
    }
    search.set(key, String(value));
  });
  return `/takim-versus?${search.toString()}`;
}

function TeamLogo({ teamId, teamName }: { teamId: string; teamName: string }) {
  return (
    <div className="flex h-20 w-20 items-center justify-center rounded-2xl border border-card-border bg-background-secondary p-3 shadow-card">
      <img src={`/api/backend/teams/${teamId}/logo`} alt={`${teamName} logosu`} className="h-full w-full object-contain" />
    </div>
  );
}

function ScoreCard({ card }: { card: TeamComparisonCard }) {
  const badgeVariant = card.winner === "home" ? "accent" : card.winner === "away" ? "warning" : "neutral";
  return (
    <Card className="space-y-3">
      <div className="flex items-center justify-between gap-3 border-b border-card-border pb-3">
        <CardTitle>{repairDisplayText(card.label)}</CardTitle>
        <Badge variant={badgeVariant} size="sm">{repairDisplayText(card.winner_label)}</Badge>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="rounded-lg border border-card-border bg-background-secondary px-3 py-3">
          <p className="text-[11px] font-black uppercase tracking-wide text-foreground-muted">Ev</p>
          <p className="mt-2 text-xl font-black text-foreground-primary">{card.home_score.toFixed(1)}</p>
        </div>
        <div className="rounded-lg border border-card-border bg-background-secondary px-3 py-3">
          <p className="text-[11px] font-black uppercase tracking-wide text-foreground-muted">Dep</p>
          <p className="mt-2 text-xl font-black text-foreground-primary">{card.away_score.toFixed(1)}</p>
        </div>
      </div>
      <CardDescription>{repairDisplayText(card.explanation)}</CardDescription>
    </Card>
  );
}

function RobotPanel({ robot }: { robot: TeamComparisonRobotOutput }) {
  return (
    <div className="grid gap-4">
      <Card className="space-y-4">
        <div className="flex flex-col gap-3 border-b border-card-border pb-4 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <CardTitle>{robot.name}</CardTitle>
            <CardDescription>{robot.confidence_note}</CardDescription>
          </div>
          <Badge variant="accent" size="sm">{robot.spec_version}</Badge>
        </div>
        <div className="grid gap-3 md:grid-cols-3">
          <div className="rounded-lg border border-card-border bg-background-secondary px-3 py-3">
            <p className="text-[11px] font-black uppercase tracking-wide text-foreground-muted">Favori</p>
            <p className="mt-2 text-sm font-black text-foreground-primary">{repairDisplayText(robot.summary_card.favorite_team)}</p>
          </div>
          <div className="rounded-lg border border-card-border bg-background-secondary px-3 py-3">
            <p className="text-[11px] font-black uppercase tracking-wide text-foreground-muted">Güç Farkı</p>
            <p className="mt-2 text-sm font-black text-foreground-primary">%{robot.summary_card.power_difference_pct.toFixed(1)}</p>
          </div>
          <div className="rounded-lg border border-card-border bg-background-secondary px-3 py-3">
            <p className="text-[11px] font-black uppercase tracking-wide text-foreground-muted">En Olası Skor</p>
            <p className="mt-2 text-sm font-black text-foreground-primary">{repairDisplayText(robot.summary_card.most_likely_score)}</p>
          </div>
        </div>
        <div className="rounded-lg border border-card-border bg-background-secondary px-4 py-3">
          <p className="text-[11px] font-black uppercase tracking-wide text-foreground-muted">{t(TR.robotMethodology)}</p>
          <p className="mt-2 text-sm font-medium leading-6 text-foreground-primary">{repairDisplayText(robot.methodology)}</p>
        </div>
      </Card>

      <div className="grid gap-4 xl:grid-cols-[0.9fr_1.1fr]">
        <Card className="space-y-4">
          <div className="border-b border-card-border pb-3">
            <CardTitle>{t(TR.robotSignals)}</CardTitle>
          </div>
          <div className="space-y-2">
            {robot.key_signals.map((signal) => (
              <div key={signal} className="rounded-lg border border-card-border bg-background-secondary px-4 py-3 text-sm font-medium leading-6 text-foreground-primary">
                - {repairDisplayText(signal)}
              </div>
            ))}
          </div>
        </Card>

        <Card className="space-y-4">
          <div className="border-b border-card-border pb-3">
            <CardTitle>{t(TR.robotBreakdown)}</CardTitle>
          </div>
          <div className="grid gap-3">
            {robot.model_breakdown.map((row) => (
              <div key={row.label} className="rounded-lg border border-card-border bg-background-secondary px-4 py-3">
                <div className="flex items-center justify-between gap-3">
                  <p className="text-xs font-black uppercase tracking-wide text-foreground-muted">{repairDisplayText(row.label)}</p>
                  <Badge variant={row.winner === "home" ? "accent" : row.winner === "away" ? "warning" : "neutral"} size="sm">
                    {repairDisplayText(row.winner_label)}
                  </Badge>
                </div>
                <div className="mt-3 grid grid-cols-2 gap-3">
                  <p className="text-sm font-black text-foreground-primary">Ev: {row.home_value.toFixed(1)}</p>
                  <p className="text-sm font-black text-foreground-primary">Dep: {row.away_value.toFixed(1)}</p>
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>

      {robot.report_blocks.map((block) => (
        <Card key={block.title} className="space-y-3">
          <div className="border-b border-card-border pb-3">
            <CardTitle>{repairDisplayText(block.title)}</CardTitle>
          </div>
          <div className="whitespace-pre-line text-sm font-medium leading-6 text-foreground-primary">
            {repairDisplayText(block.body)}
          </div>
        </Card>
      ))}
    </div>
  );
}

export default async function TeamVersusPage({ searchParams }: TeamVersusPageProps) {
  const params = (await searchParams) ?? {};
  const homeTeamId = normalizeValue(params.home_team_id);
  const awayTeamId = normalizeValue(params.away_team_id);
  const selectedScope = normalizeValue(params.scope) || "primary_current";
  const selectedRobot = ["ana", "bma", "gma"].includes(normalizeValue(params.robot).toLowerCase())
    ? normalizeValue(params.robot).toLowerCase()
    : "ana";
  const selectedWindow = [5, 10, 20].includes(Number(params.data_window)) ? Number(params.data_window) : 10;
  const refresh = normalizeValue(params.refresh).toLowerCase() === "true";

  const meta = await getTeamComparisonMeta();

  let comparison: TeamComparisonResponse | null = null;
  let fetchError: string | null = null;
  if (homeTeamId && awayTeamId) {
    try {
      comparison = await getTeamComparison({
        homeTeamId,
        awayTeamId,
        scope: selectedScope,
        dataWindow: selectedWindow,
        refresh,
      });
    } catch (error) {
      fetchError = error instanceof Error ? error.message : t(TR.comparisonErrorTitle);
    }
  }

  const activeRobot = comparison?.robots[selectedRobot as keyof TeamComparisonResponse["robots"]] ?? null;
  const homeName = repairDisplayText(comparison?.header_summary.home_team.name) || "";
  const awayName = repairDisplayText(comparison?.header_summary.away_team.name) || "";

  return (
    <section className="space-y-8 animate-fade-in">
      <div className="flex flex-col gap-4 border-b-2 border-card-border pb-6 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <div className="mb-2 flex items-center gap-3">
            <Badge variant="accent" size="sm">{t(TR.teamVersus)}</Badge>
            <span className="text-xs font-black uppercase tracking-[0.3em] text-accent">Betlify</span>
          </div>
          <h1 className="text-4xl font-black uppercase tracking-tight text-white">{t(TR.teamVersusTitle)}</h1>
          <p className="mt-2 max-w-4xl text-sm font-medium uppercase tracking-wide text-foreground-tertiary">
            {t(TR.teamVersusBody)}
          </p>
        </div>
        {comparison && (
          <div className="flex flex-wrap gap-2">
            <Badge variant="neutral" size="md">{t(TR.confidence)}: %{Math.round(comparison.confidence.confidence_score)}</Badge>
            <Badge variant="warning" size="md">{t(TR.dataQuality)}: %{Math.round(comparison.confidence.data_quality_score)}</Badge>
            <Badge variant={comparison.meta.cache_hit ? "accent" : "success"} size="md">{comparison.meta.cache_hit ? "CACHE" : "CANLI HESAP"}</Badge>
          </div>
        )}
      </div>

      <ComparisonControls
        meta={meta}
        initialHomeTeamId={homeTeamId}
        initialAwayTeamId={awayTeamId}
        initialHomeTeamName={homeName}
        initialAwayTeamName={awayName}
        initialScope={selectedScope}
        initialDataWindow={selectedWindow}
        initialRobot={selectedRobot}
      />

      {!homeTeamId || !awayTeamId ? (
        <Card className="space-y-3">
          <div className="border-b border-card-border pb-4">
            <CardTitle>{t(TR.comparisonGuideTitle)}</CardTitle>
          </div>
          <CardDescription>{t(TR.comparisonGuideBody)}</CardDescription>
        </Card>
      ) : fetchError ? (
        <Card className="space-y-3 border-error/40">
          <div className="border-b border-card-border pb-4">
            <CardTitle>{t(TR.comparisonErrorTitle)}</CardTitle>
          </div>
          <div className="text-sm font-medium text-error">{fetchError}</div>
        </Card>
      ) : comparison ? (
        <>
          <Card className="space-y-5 border-2 border-accent shadow-accent">
            <div className="flex flex-col gap-6 lg:flex-row lg:items-center lg:justify-between">
              <div className="flex items-center gap-4">
                <TeamLogo teamId={comparison.header_summary.home_team.id} teamName={repairDisplayText(comparison.header_summary.home_team.name)} />
                <div>
                  <p className="text-xs font-black uppercase tracking-[0.3em] text-accent">EV SAHİBİ</p>
                  <h2 className="mt-2 text-2xl font-black uppercase tracking-tight text-white">{repairDisplayText(comparison.header_summary.home_team.name)}</h2>
                  <p className="mt-1 text-xs font-bold uppercase tracking-wide text-foreground-muted">{repairDisplayText(comparison.header_summary.home_team.league)}</p>
                </div>
              </div>
              <div className="text-center">
                <p className="text-5xl font-black uppercase tracking-tight text-white">VS</p>
                <p className="mt-2 text-xs font-bold uppercase tracking-[0.3em] text-foreground-muted">{repairDisplayText(comparison.header_summary.league_context)}</p>
              </div>
              <div className="flex items-center gap-4 lg:flex-row-reverse">
                <TeamLogo teamId={comparison.header_summary.away_team.id} teamName={repairDisplayText(comparison.header_summary.away_team.name)} />
                <div className="lg:text-right">
                  <p className="text-xs font-black uppercase tracking-[0.3em] text-accent">DEPLASMAN</p>
                  <h2 className="mt-2 text-2xl font-black uppercase tracking-tight text-white">{repairDisplayText(comparison.header_summary.away_team.name)}</h2>
                  <p className="mt-1 text-xs font-bold uppercase tracking-wide text-foreground-muted">{repairDisplayText(comparison.header_summary.away_team.league)}</p>
                </div>
              </div>
            </div>
          </Card>

          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            {(comparison.shared_comparison.cards ?? []).slice(0, 4).map((card) => (
              <ScoreCard key={card.key} card={card} />
            ))}
          </div>

          <Card className="space-y-4">
            <div className="border-b border-card-border pb-4">
              <CardTitle>{t(TR.axisBreakdown)}</CardTitle>
            </div>
            <div className="grid gap-3 lg:grid-cols-2">
              {comparison.shared_comparison.axes.map((axis) => (
                <div key={axis.key} className="rounded-lg border border-card-border bg-background-secondary px-4 py-3">
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-xs font-black uppercase tracking-wide text-foreground-muted">{repairDisplayText(axis.label)}</p>
                    <Badge variant={axis.winner === "home" ? "accent" : axis.winner === "away" ? "warning" : "neutral"} size="sm">
                      {repairDisplayText(axis.winner_label)}
                    </Badge>
                  </div>
                  <div className="mt-3 grid grid-cols-2 gap-3">
                    <p className="text-sm font-black text-foreground-primary">Ev: {axis.home_score.toFixed(1)}</p>
                    <p className="text-sm font-black text-foreground-primary">Dep: {axis.away_score.toFixed(1)}</p>
                  </div>
                  <p className="mt-3 text-xs font-medium leading-5 text-foreground-muted">{repairDisplayText(axis.explanation)}</p>
                </div>
              ))}
            </div>
          </Card>

          <div className="grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
            <Card className="space-y-4">
              <div className="border-b border-card-border pb-4">
                <CardTitle>{t(TR.topScorelines)}</CardTitle>
              </div>
              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                {comparison.probability_block.top_5_scorelines.map((scoreline) => (
                  <div key={scoreline.score} className="rounded-lg border border-card-border bg-background-secondary px-4 py-3">
                    <p className="text-xs font-black uppercase tracking-wide text-foreground-muted">Skor</p>
                    <p className="mt-2 text-xl font-black text-foreground-primary">{repairDisplayText(scoreline.score)}</p>
                    <p className="mt-1 text-xs font-bold text-accent">%{(scoreline.probability * 100).toFixed(1)}</p>
                  </div>
                ))}
              </div>
              <div className="grid gap-3 md:grid-cols-3">
                <div className="rounded-lg border border-card-border bg-background-secondary px-4 py-3">
                  <p className="text-[11px] font-black uppercase tracking-wide text-foreground-muted">1X2</p>
                  <p className="mt-2 text-sm font-black text-foreground-primary">
                    Ev %{(comparison.probability_block.one_x_two.home * 100).toFixed(1)} | X %{(comparison.probability_block.one_x_two.draw * 100).toFixed(1)} | Dep %{(comparison.probability_block.one_x_two.away * 100).toFixed(1)}
                  </p>
                </div>
                <div className="rounded-lg border border-card-border bg-background-secondary px-4 py-3">
                  <p className="text-[11px] font-black uppercase tracking-wide text-foreground-muted">Üst 2.5</p>
                  <p className="mt-2 text-sm font-black text-foreground-primary">%{(comparison.probability_block.totals.over_2_5 * 100).toFixed(1)}</p>
                </div>
                <div className="rounded-lg border border-card-border bg-background-secondary px-4 py-3">
                  <p className="text-[11px] font-black uppercase tracking-wide text-foreground-muted">KG Var</p>
                  <p className="mt-2 text-sm font-black text-foreground-primary">%{(comparison.probability_block.btts.yes * 100).toFixed(1)}</p>
                </div>
              </div>
            </Card>

            <Card className="space-y-4">
              <div className="border-b border-card-border pb-4">
                <CardTitle>{t(TR.scenarios)}</CardTitle>
              </div>
              <div className="grid gap-3">
                {comparison.probability_block.top_3_scenarios.map((scenario) => (
                  <div key={scenario.key} className="rounded-lg border border-card-border bg-background-secondary px-4 py-3">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="text-sm font-black text-foreground-primary">{repairDisplayText(scenario.title)}</p>
                        <p className="mt-1 text-xs font-medium text-foreground-muted">Tempo: {repairDisplayText(scenario.tempo)} | İlk gol: {repairDisplayText(scenario.first_goal_window)}</p>
                      </div>
                      <Badge variant="accent" size="sm">%{scenario.probability_score.toFixed(1)}</Badge>
                    </div>
                    <div className="mt-3 space-y-1 text-xs font-medium leading-5 text-foreground-primary">
                      {scenario.reasons.map((reason) => (
                        <p key={reason}>- {repairDisplayText(reason)}</p>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </Card>
          </div>

          <Card className="space-y-4">
            <div className="flex flex-wrap items-center gap-3 border-b border-card-border pb-4">
              <CardTitle>{t(TR.robotReports)}</CardTitle>
              <div className="flex flex-wrap gap-2">
                {(["ana", "bma", "gma"] as const).map((robotKey) => (
                  <Link
                    key={robotKey}
                    href={buildHref({
                      home_team_id: homeTeamId,
                      away_team_id: awayTeamId,
                      scope: selectedScope,
                      data_window: selectedWindow,
                      robot: robotKey,
                    })}
                    className={[
                      "inline-flex items-center rounded-md border px-3 py-2 text-xs font-black uppercase tracking-wide transition-colors",
                      robotKey === selectedRobot
                        ? "border-accent bg-accent text-white"
                        : "border-card-border bg-background-secondary text-foreground-muted hover:border-accent/40 hover:text-accent",
                    ].join(" ")}
                  >
                    {robotKey.toUpperCase()}
                  </Link>
                ))}
              </div>
            </div>
            {activeRobot ? <RobotPanel robot={activeRobot} /> : null}
          </Card>

          <Card className="space-y-4">
            <div className="border-b border-card-border pb-4">
              <CardTitle>{t(TR.dataGaps)}</CardTitle>
            </div>
            <div className="grid gap-2 text-sm font-medium text-foreground-primary">
              {comparison.data_gaps.length ? comparison.data_gaps.map((gap) => <p key={gap}>- {repairDisplayText(gap)}</p>) : <p>- Veri boşluğu işaretlenmedi.</p>}
            </div>
          </Card>
        </>
      ) : null}
    </section>
  );
}
