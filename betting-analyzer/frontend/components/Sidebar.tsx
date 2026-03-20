"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

const navItems = [
  { href: "/dashboard", label: "Dashboard", icon: "🏠" },
  { href: "/coupon", label: "Kupon", icon: "🎫" },
  { href: "/history", label: "Geçmiş", icon: "📊" },
  { href: "/settings", label: "Ayarlar", icon: "⚙️" }
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <>
      <aside className="hidden w-64 shrink-0 border-r border-white/5 bg-[#141420] px-4 py-6 md:block">
        <div className="mb-8 rounded-2xl border border-[#6366f1]/20 bg-[#19192a] p-4">
          <p className="text-xs uppercase tracking-[0.2em] text-[#8f92ff]">Betlify</p>
          <h1 className="mt-2 text-2xl font-bold text-white">Bahis Paneli</h1>
        </div>
        <nav className="space-y-2">
          {navItems.map((item) => {
            const active = pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "flex items-center gap-3 rounded-xl px-3 py-2 text-sm transition",
                  active
                    ? "bg-[#232336] text-white ring-1 ring-[#6366f1]/35"
                    : "text-zinc-300 hover:bg-[#1d1d2d] hover:text-white"
                )}
              >
                <span>{item.icon}</span>
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>
      </aside>

      <nav className="sticky top-0 z-20 block border-b border-white/5 bg-[#141420]/95 px-3 py-2 backdrop-blur md:hidden">
        <div className="mb-2 flex items-center justify-between">
          <p className="text-sm font-semibold text-white">Betlify</p>
          <p className="text-xs text-zinc-400">Bahis Paneli</p>
        </div>
        <div className="flex gap-2 overflow-x-auto">
          {navItems.map((item) => {
            const active = pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "inline-flex min-w-fit items-center gap-2 rounded-lg px-3 py-1.5 text-xs transition",
                  active ? "bg-[#232336] text-white" : "bg-[#1a1a24] text-zinc-300"
                )}
              >
                <span>{item.icon}</span>
                <span>{item.label}</span>
              </Link>
            );
          })}
        </div>
      </nav>
    </>
  );
}
