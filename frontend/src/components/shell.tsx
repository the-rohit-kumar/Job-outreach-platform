"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  BarChart3,
  ClipboardCheck,
  Gauge,
  HelpCircle,
  LayoutList,
  LogOut,
  Plug,
  Settings2,
  User,
  Users,
} from "lucide-react";
import { api, setUnauthorizedHandler } from "@/lib/api";
import type { AuthStatus } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { ThemeToggle } from "@/components/theme-toggle";

const NAV = [
  { href: "/", label: "Dashboard", icon: Gauge },
  { href: "/profile", label: "Profile", icon: User },
  { href: "/sources", label: "Sources", icon: Plug },
  { href: "/leads", label: "Leads", icon: Users },
  { href: "/review", label: "Review Queue", icon: ClipboardCheck },
  { href: "/tracker", label: "Tracker", icon: LayoutList },
  { href: "/analytics", label: "Analytics", icon: BarChart3 },
  { href: "/settings", label: "Settings", icon: Settings2 },
  { href: "/help", label: "Help", icon: HelpCircle },
];

export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [status, setStatus] = React.useState<AuthStatus | null>(null);

  React.useEffect(() => {
    setUnauthorizedHandler(() => router.replace("/login"));
    return () => setUnauthorizedHandler(null);
  }, [router]);

  React.useEffect(() => {
    let cancelled = false;
    api<AuthStatus>("/api/auth/status")
      .then(async (s) => {
        if (cancelled) return;
        if (s.needs_setup || !s.user) {
          router.replace("/login");
          return;
        }
        setStatus(s);
      })
      .catch(() => {
        if (!cancelled) router.replace("/login");
      });
    return () => {
      cancelled = true;
    };
  }, [router]);

  async function signOut() {
    await api("/api/auth/logout", { method: "POST" });
    router.replace("/login");
  }

  if (!status) {
    return (
      <div className="flex min-h-screen items-center justify-center text-sm text-slate-500 dark:text-slate-400 bg-slate-50 dark:bg-slate-950">
        Loading…
      </div>
    );
  }

  return (
    <div className="flex min-h-screen bg-slate-50 dark:bg-slate-950 text-slate-900 dark:text-slate-100 transition-colors">
      <aside className="fixed inset-y-0 left-0 z-30 flex w-56 flex-col border-r border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
        <div className="flex h-14 items-center justify-between border-b border-slate-200 px-4 dark:border-slate-800">
          <span className="text-sm font-semibold tracking-tight">OutreachHub</span>
          <ThemeToggle />
        </div>
        <nav className="flex-1 space-y-0.5 overflow-y-auto p-2">
          {NAV.map(({ href, label, icon: Icon }) => {
            const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                className={`flex items-center gap-2 rounded-md px-2.5 py-2 text-sm transition-colors ${
                  active
                    ? "bg-slate-900 text-slate-50 shadow-xs dark:bg-slate-800 dark:text-slate-100 font-medium"
                    : "text-slate-700 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800/60 dark:hover:text-slate-100"
                }`}
              >
                <Icon className="h-4 w-4" />
                {label}
              </Link>
            );
          })}
        </nav>
        <div className="border-t border-slate-200 p-3 dark:border-slate-800 space-y-2">
          <Link
            href="/profile"
            className="flex items-center gap-2 rounded px-2 py-1 text-xs text-slate-600 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800 transition-colors"
          >
            <User className="h-3.5 w-3.5 text-slate-500" />
            <span className="truncate">
              signed in as <span className="font-medium text-slate-800 dark:text-slate-200">{status.user?.username}</span>
            </span>
          </Link>
          <Button variant="outline" size="sm" className="w-full" onClick={signOut}>
            <LogOut /> Sign out
          </Button>
        </div>
      </aside>
      <main className="ml-56 flex-1 px-8 py-8">
        <div className="mx-auto max-w-6xl">{children}</div>
      </main>
    </div>
  );
}
