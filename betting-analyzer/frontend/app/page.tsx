import Link from "next/link";

const quickActions = [
  {
    title: "Dashboard",
    description: "Gunluk fiksturleri, model sinyallerini ve oran degisimlerini tek ekranda izle.",
    href: "/dashboard"
  },
  {
    title: "Maclar",
    description: "Tum maclari detayli filtrele, model ciktilarini karsilastir ve firsatlari bul.",
    href: "/matches"
  },
  {
    title: "Kupon",
    description: "Secimlerini biriktir, olasi getiriyi gor ve kuponunu daha kontrollu kur.",
    href: "/coupon"
  }
] as const;

const pillars = [
  {
    label: "Veri Katmani",
    text: "Sofascore, hava durumu ve oran kaynaklarini birlestiren merkezi veri akisi."
  },
  {
    label: "Modelleme",
    text: "xG, form, piyasa hareketi ve risk filtreleriyle desteklenen tahmin boru hatti."
  },
  {
    label: "Operasyon",
    text: "Kayitli sonuc gecmisi, geri test ve robot ciktilariyla surekli takip."
  }
] as const;

const stats = [
  { label: "Takip Modulu", value: "8+" },
  { label: "Analiz Asamasi", value: "9" },
  { label: "Ana Ekran", value: "6" }
] as const;

export default function HomePage() {
  return (
    <div className="space-y-6 md:space-y-8">
      <section className="relative overflow-hidden rounded-3xl border border-card-border bg-gradient-to-br from-background-card via-background-secondary to-background px-6 py-8 shadow-card md:px-10 md:py-12">
        <div className="pointer-events-none absolute -right-20 -top-24 h-56 w-56 rounded-full bg-accent/20 blur-3xl" />
        <div className="pointer-events-none absolute -left-24 bottom-0 h-52 w-52 rounded-full bg-success/15 blur-3xl" />

        <div className="relative z-10 grid gap-8 lg:grid-cols-[1.25fr_1fr] lg:items-start">
          <div className="space-y-6">
            <span className="inline-flex items-center rounded-full border border-accent/40 bg-accent/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em] text-accent-secondary">
              Betlify Control Center
            </span>

            <div className="space-y-3">
              <h1 className="text-3xl font-extrabold tracking-tight text-foreground-primary md:text-5xl">
                Bahis kararlarini veriyle netlestir.
              </h1>
              <p className="max-w-2xl text-sm text-foreground-tertiary md:text-base">
                Betlify; oran, form ve mac baglami verilerini bir araya getirip, tum is akisini tek panelde yonetmen icin tasarlandi.
              </p>
            </div>

            <div className="flex flex-wrap gap-3">
              <Link
                href="/dashboard"
                className="inline-flex items-center justify-center rounded-xl bg-accent px-5 py-2.5 text-sm font-semibold text-background transition hover:bg-accent-secondary"
              >
                Dashboarda Git
              </Link>
              <Link
                href="/takim-versus"
                className="inline-flex items-center justify-center rounded-xl border border-card-border bg-background-card px-5 py-2.5 text-sm font-semibold text-foreground-secondary transition hover:border-accent/50 hover:text-foreground-primary"
              >
                Takim Karsilastir
              </Link>
              <Link
                href="/history"
                className="inline-flex items-center justify-center rounded-xl border border-card-border px-5 py-2.5 text-sm font-semibold text-foreground-tertiary transition hover:border-card-hover hover:text-foreground-primary"
              >
                Sonuclar
              </Link>
            </div>

            <div className="grid gap-3 sm:grid-cols-3">
              {stats.map((item) => (
                <div key={item.label} className="rounded-2xl border border-card-border bg-background-card/70 p-4">
                  <p className="text-2xl font-bold text-foreground-primary">{item.value}</p>
                  <p className="text-xs text-foreground-muted">{item.label}</p>
                </div>
              ))}
            </div>
          </div>

          <div className="space-y-3">
            {pillars.map((pillar) => (
              <article
                key={pillar.label}
                className="rounded-2xl border border-card-border bg-background-card/80 p-4 shadow-card"
              >
                <p className="text-xs font-semibold uppercase tracking-[0.14em] text-accent-secondary">
                  {pillar.label}
                </p>
                <p className="mt-2 text-sm text-foreground-tertiary">{pillar.text}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="grid gap-4 md:grid-cols-3">
        {quickActions.map((action) => (
          <Link
            key={action.href}
            href={action.href}
            className="group rounded-2xl border border-card-border bg-background-card p-5 shadow-card transition hover:-translate-y-0.5 hover:border-accent/40 hover:bg-background-elevated hover:shadow-card-hover"
          >
            <div className="space-y-2">
              <h2 className="text-lg font-semibold text-foreground-primary transition group-hover:text-accent-secondary">
                {action.title}
              </h2>
              <p className="text-sm text-foreground-tertiary">{action.description}</p>
            </div>
            <span className="mt-4 inline-flex text-xs font-semibold uppercase tracking-[0.12em] text-accent">
              Ac
            </span>
          </Link>
        ))}
      </section>
    </div>
  );
}
