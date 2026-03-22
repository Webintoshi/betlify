import Link from "next/link";
import { notFound } from "next/navigation";
import { Badge } from "@/components/ui/badge";
import { Card, CardDescription, CardTitle } from "@/components/ui/card";
import { getTeam } from "@/lib/api";

type TeamDetailPageProps = {
  params: Promise<{
    id: string;
  }>;
};

function normalizeValue(value?: string | null): string {
  return String(value ?? "").trim();
}

function repairMojibakeText(value?: string | null): string {
  const text = normalizeValue(value);
  if (!text) {
    return "";
  }

  const decodedEscapes = text.replace(/\\u([0-9a-fA-F]{4})/g, (_, hex: string) =>
    String.fromCharCode(Number.parseInt(hex, 16))
  );
  const baseText = decodedEscapes !== text ? decodedEscapes : text;

  if (!/[ÃÄÅ]/.test(baseText)) {
    return baseText;
  }

  try {
    const bytes = Uint8Array.from(Array.from(baseText), (character) => character.charCodeAt(0) & 0xff);
    const repaired = new TextDecoder("utf-8").decode(bytes).trim();
    return repaired || baseText;
  } catch {
    return baseText;
  }
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
  const teamName = repairMojibakeText(team.name);
  const coachName = repairMojibakeText(team.coach_name) || "Bilinmiyor";
  const leagueName = repairMojibakeText(team.league) || "Bilinmeyen Lig";
  const countryName = repairMojibakeText(team.country) || "Bilinmiyor";
  const syncStatus = normalizeValue(team.profile_sync_status);
  const statusLabel = syncStatus === "ready" ? "Hazır" : syncStatus === "stale" ? "Güncellenecek" : "Bekliyor";
  const badgeVariant = syncStatus === "ready" ? "success" : syncStatus === "stale" ? "warning" : "neutral";

  return (
    <section className="space-y-8 animate-fade-in">
      <div className="flex flex-col gap-4 border-b-2 border-card-border pb-6 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex items-center gap-5">
          <TeamLogo teamId={team.id} teamName={teamName} />
          <div>
            <div className="mb-3 flex flex-wrap items-center gap-3">
              <Badge variant="accent" size="sm">
                Takım Profili
              </Badge>
              <Badge variant={badgeVariant} size="sm">
                {statusLabel}
              </Badge>
            </div>
            <h1 className="text-display-sm text-foreground-primary uppercase tracking-tight">{teamName}</h1>
            <p className="mt-2 text-sm font-bold uppercase tracking-wide text-foreground-muted">
              {leagueName} • {countryName}
            </p>
          </div>
        </div>

        <Link
          href="/takimler"
          className="inline-flex items-center justify-center rounded-lg border border-card-border px-4 py-3 text-xs font-black uppercase tracking-wide text-foreground-secondary transition-colors duration-150 hover:border-accent hover:text-accent"
        >
          Takımlara Dön
        </Link>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1.2fr_0.8fr]">
        <Card className="space-y-5">
          <div className="border-b border-card-border pb-4">
            <CardTitle>Genel Bilgiler</CardTitle>
            <CardDescription className="mt-2 normal-case tracking-normal">
              Bu sayfa takım kartındaki temel bilgileri sistem içinden gösterir. Kullanıcıyı dış kaynağa göndermiyoruz.
            </CardDescription>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <div className="rounded-lg border border-card-border bg-background-secondary px-4 py-3">
              <p className="text-xs font-black uppercase tracking-wide text-foreground-muted">Takım</p>
              <p className="mt-2 text-sm font-bold text-foreground-primary">{teamName}</p>
            </div>
            <div className="rounded-lg border border-card-border bg-background-secondary px-4 py-3">
              <p className="text-xs font-black uppercase tracking-wide text-foreground-muted">Lig</p>
              <p className="mt-2 text-sm font-bold text-foreground-primary">{leagueName}</p>
            </div>
            <div className="rounded-lg border border-card-border bg-background-secondary px-4 py-3">
              <p className="text-xs font-black uppercase tracking-wide text-foreground-muted">Ülke</p>
              <p className="mt-2 text-sm font-bold text-foreground-primary">{countryName}</p>
            </div>
            <div className="rounded-lg border border-card-border bg-background-secondary px-4 py-3">
              <p className="text-xs font-black uppercase tracking-wide text-foreground-muted">Teknik Direktör</p>
              <p className="mt-2 text-sm font-bold text-foreground-primary">{coachName}</p>
            </div>
          </div>
        </Card>

        <Card className="space-y-5">
          <div className="border-b border-card-border pb-4">
            <CardTitle>Sistem Kaydı</CardTitle>
            <CardDescription className="mt-2 normal-case tracking-normal">
              Takım verisi SofaScore cache katmanından alınıyor ve sistem içinde saklanıyor.
            </CardDescription>
          </div>

          <div className="grid gap-4">
            <div className="rounded-lg border border-card-border bg-background-secondary px-4 py-3">
              <p className="text-xs font-black uppercase tracking-wide text-foreground-muted">SofaScore ID</p>
              <p className="mt-2 text-sm font-bold text-foreground-primary">{team.sofascore_id ?? "-"}</p>
            </div>
            <div className="rounded-lg border border-card-border bg-background-secondary px-4 py-3">
              <p className="text-xs font-black uppercase tracking-wide text-foreground-muted">Durum</p>
              <p className="mt-2 text-sm font-bold text-foreground-primary">{statusLabel}</p>
            </div>
            <div className="rounded-lg border border-card-border bg-background-secondary px-4 py-3">
              <p className="text-xs font-black uppercase tracking-wide text-foreground-muted">Son Eşitleme</p>
              <p className="mt-2 text-sm font-bold text-foreground-primary">{normalizeValue(team.profile_last_fetched_at) || "Henüz yok"}</p>
            </div>
          </div>
        </Card>
      </div>
    </section>
  );
}
