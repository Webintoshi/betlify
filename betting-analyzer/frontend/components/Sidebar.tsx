"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

const navItems = [
  {
    href: "/dashboard",
    label: "Dashboard",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" />
      </svg>
    )
  },
  {
    href: "/takimler",
    label: "Takimlar",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 20h5V10a2 2 0 00-.586-1.414l-7-7a2 2 0 00-2.828 0l-7 7A2 2 0 004 10v10h5m8 0v-6a2 2 0 00-2-2H9a2 2 0 00-2 2v6m10 0H7" />
      </svg>
    )
  },
  {
    href: "/takim-versus",
    label: "Tak\u0131m Versus",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 17l4-4-4-4m6 8l4-4-4-4" />
      </svg>
    )
  },
  {
    href: "/coupon",
    label: "Kupon",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 5v2m0 4v2m0 4v2M5 5a2 2 0 00-2 2v3a2 2 0 110 4v3a2 2 0 002 2h14a2 2 0 002-2v-3a2 2 0 110-4V7a2 2 0 00-2-2H5z" />
      </svg>
    )
  },
  {
    href: "/history",
    label: "Gecmis",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    )
  },
  {
    href: "/backtest",
    label: "Backtest",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 17l-4-4m0 0l4-4m-4 4h14M5 21h14" />
      </svg>
    )
  },
  {
    href: "/settings",
    label: "Ayarlar",
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
      </svg>
    )
  }
];

export function Sidebar() {
  const pathname = usePathname();
  const [lastUpdated, setLastUpdated] = useState<string>("--:--");

  useEffect(() => {
    const formatter = new Intl.DateTimeFormat("tr-TR", { hour: "2-digit", minute: "2-digit" });
    const updateClock = () => setLastUpdated(formatter.format(new Date()));

    updateClock();
    const intervalId = window.setInterval(updateClock, 60_000);
    return () => window.clearInterval(intervalId);
  }, []);

  return (
    <>
      {/* Desktop Sidebar - Solid Design */}
      <aside className="hidden md:flex w-72 shrink-0 flex-col bg-card border-r-2 border-card-border">
        {/* Logo Section */}
        <div className="p-6 border-b-2 border-card-border">
          <div className="bg-background-secondary rounded-xl p-5 border-2 border-accent/30">
            <p className="text-xs font-black uppercase tracking-[0.3em] text-accent">
              Betlify
            </p>
            <h1 className="mt-2 text-2xl font-black text-white tracking-tight">
              Bahis Paneli
            </h1>
            <p className="mt-1 text-xs font-bold text-foreground-tertiary uppercase tracking-wide">
              Profesyonel Analiz
            </p>
          </div>
        </div>

        {/* Navigation */}
        <nav className="flex-1 p-4 space-y-2">
          {navItems.map((item) => {
            const active = pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "group flex items-center gap-3 rounded-lg px-4 py-3 text-sm font-bold uppercase tracking-wide transition-all duration-150",
                  active
                    ? ["bg-accent text-white", "border-2 border-accent", "shadow-accent"].join(" ")
                    : [
                        "text-foreground-tertiary",
                        "bg-transparent",
                        "border-2 border-transparent",
                        "hover:bg-card-hover",
                        "hover:text-accent",
                        "hover:border-accent/30"
                      ].join(" ")
                )}
              >
                <span
                  className={cn(
                    "transition-transform duration-150",
                    active ? "text-white scale-110" : "text-foreground-muted group-hover:text-accent group-hover:scale-110"
                  )}
                >
                  {item.icon}
                </span>
                <span>{item.label}</span>

                {active && <span className="ml-auto w-2 h-2 rounded-full bg-white" />}
              </Link>
            );
          })}
        </nav>

        {/* Footer Info */}
        <div className="p-4 border-t-2 border-card-border">
          <div className="rounded-lg bg-background-secondary p-4 border border-card-border">
            <div className="flex items-center gap-2 mb-2">
              <span className="w-2.5 h-2.5 rounded-full bg-success animate-pulse" />
              <span className="text-xs font-bold text-success uppercase tracking-wide">Sistem Aktif</span>
            </div>
            <p className="text-[10px] font-medium text-foreground-muted">
              Son guncelleme: {lastUpdated}
            </p>
          </div>
        </div>
      </aside>

      {/* Mobile Navigation - Solid */}
      <nav className="sticky top-0 z-50 md:hidden bg-card border-b-2 border-card-border">
        {/* Header */}
        <div className="px-4 py-3">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-black text-white uppercase tracking-wider">Betlify</p>
              <p className="text-[10px] font-bold text-accent uppercase tracking-widest">Profesyonel Analiz</p>
            </div>
            <div className="flex items-center gap-2">
              <span className="w-2.5 h-2.5 rounded-full bg-success animate-pulse" />
              <span className="text-xs font-bold text-success uppercase">Aktif</span>
            </div>
          </div>
        </div>

        {/* Tab Navigation */}
        <div className="px-4 py-2 bg-background-secondary border-t border-card-border overflow-x-auto">
          <div className="flex gap-2">
            {navItems.map((item) => {
              const active = pathname.startsWith(item.href);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    "flex items-center gap-2 px-4 py-2 rounded-md text-xs font-bold uppercase tracking-wide whitespace-nowrap transition-all duration-150 border-2",
                    active
                      ? "bg-accent text-white border-accent shadow-accent"
                      : "bg-card text-foreground-tertiary border-card-border hover:border-accent/50 hover:text-accent"
                  )}
                >
                  <span className={active ? "text-white" : "text-accent"}>{item.icon}</span>
                  <span>{item.label}</span>
                </Link>
              );
            })}
          </div>
        </div>
      </nav>
    </>
  );
}
