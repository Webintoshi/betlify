"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

const navItems = [
  { 
    href: "/dashboard", 
    label: "Dashboard", 
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
      </svg>
    )
  },
  { 
    href: "/coupon", 
    label: "Kupon", 
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 5v2m0 4v2m0 4v2M5 5a2 2 0 00-2 2v3a2 2 0 110 4v3a2 2 0 002 2h14a2 2 0 002-2v-3a2 2 0 110-4V7a2 2 0 00-2-2H5z" />
      </svg>
    )
  },
  { 
    href: "/history", 
    label: "Geçmiş", 
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
      </svg>
    )
  },
  { 
    href: "/settings", 
    label: "Ayarlar", 
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
      </svg>
    )
  }
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <>
      {/* Desktop Sidebar */}
      <aside className="hidden md:flex w-72 shrink-0 flex-col border-r border-white/[0.04] bg-card/50 backdrop-blur-2xl">
        {/* Logo Section */}
        <div className="p-6 border-b border-white/[0.04]">
          <div className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-accent/20 to-accent-secondary/10 p-5 border border-accent/20">
            {/* Glow effect */}
            <div className="absolute -top-10 -right-10 w-20 h-20 bg-accent/30 rounded-full blur-2xl" />
            <div className="absolute -bottom-10 -left-10 w-16 h-16 bg-accent-secondary/20 rounded-full blur-xl" />
            
            <div className="relative">
              <p className="text-xs font-semibold uppercase tracking-[0.25em] text-accent">
                Betlify
              </p>
              <h1 className="mt-2 text-2xl font-bold text-white tracking-tight">
                Bahis Paneli
              </h1>
              <p className="mt-1 text-xs text-foreground-tertiary">
                Premium Analiz Platformu
              </p>
            </div>
          </div>
        </div>

        {/* Navigation */}
        <nav className="flex-1 p-4 space-y-1">
          {navItems.map((item, index) => {
            const active = pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "group flex items-center gap-3 rounded-xl px-4 py-3 text-sm font-medium transition-all duration-300 ease-premium",
                  "relative overflow-hidden",
                  active 
                    ? [
                        "bg-accent/10 text-white",
                        "border border-accent/30",
                        "shadow-[0_0_20px_rgba(99,102,241,0.15)]"
                      ].join(" ")
                    : [
                        "text-foreground-tertiary",
                        "hover:bg-white/[0.04]",
                        "hover:text-foreground-secondary",
                        "border border-transparent"
                      ].join(" ")
                )}
              >
                {/* Active indicator line */}
                {active && (
                  <span className="absolute left-0 top-1/2 -translate-y-1/2 w-1 h-8 bg-gradient-to-b from-accent to-accent-secondary rounded-r-full" />
                )}
                
                {/* Icon */}
                <span className={cn(
                  "transition-transform duration-300",
                  active ? "text-accent" : "text-foreground-muted group-hover:text-foreground-secondary",
                  "group-hover:scale-110"
                )}>
                  {item.icon}
                </span>
                
                {/* Label */}
                <span className="relative">
                  {item.label}
                  {/* Hover underline effect */}
                  {!active && (
                    <span className="absolute -bottom-0.5 left-0 w-0 h-px bg-accent/50 transition-all duration-300 group-hover:w-full" />
                  )}
                </span>

                {/* Active glow */}
                {active && (
                  <span className="absolute inset-0 bg-gradient-to-r from-accent/5 to-transparent pointer-events-none" />
                )}
              </Link>
            );
          })}
        </nav>

        {/* Footer Info */}
        <div className="p-4 border-t border-white/[0.04]">
          <div className="rounded-xl bg-white/[0.02] p-4 border border-white/[0.04]">
            <div className="flex items-center gap-2 mb-2">
              <span className="w-2 h-2 rounded-full bg-success animate-pulse" />
              <span className="text-xs font-medium text-foreground-secondary">Sistem Aktif</span>
            </div>
            <p className="text-[10px] text-foreground-muted">
              Son güncelleme: {new Date().toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' })}
            </p>
          </div>
        </div>
      </aside>

      {/* Mobile Navigation */}
      <nav className="sticky top-0 z-50 md:hidden">
        {/* Header */}
        <div className="px-4 py-3 border-b border-white/[0.04] bg-background/95 backdrop-blur-xl">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-semibold text-white">Betlify</p>
              <p className="text-[10px] text-foreground-muted">Premium Analiz</p>
            </div>
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-success animate-pulse" />
              <span className="text-xs text-foreground-tertiary">Aktif</span>
            </div>
          </div>
        </div>
        
        {/* Tab Navigation */}
        <div className="px-4 py-2 border-b border-white/[0.04] bg-card/80 backdrop-blur-xl overflow-x-auto">
          <div className="flex gap-2">
            {navItems.map((item) => {
              const active = pathname.startsWith(item.href);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    "flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-medium whitespace-nowrap transition-all duration-200",
                    active
                      ? "bg-accent text-white shadow-glow-sm"
                      : "bg-white/[0.04] text-foreground-tertiary hover:bg-white/[0.08]"
                  )}
                >
                  <span className={active ? "text-white" : "text-foreground-muted"}>
                    {item.icon}
                  </span>
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
