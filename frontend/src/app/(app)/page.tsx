"use client";

import * as React from "react";
import Link from "next/link";
import { Check, CircleDashed, RefreshCw } from "lucide-react";
import { api } from "@/lib/api";
import type { OnboardingItem } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Progress } from "@/components/progress";

const ROUTINE = [
  { time: "Morning (10 min)", text: "Check dashboard counts and source errors, run failed sources." },
  {
    time: "Review session (25-30 min)",
    text: "A approve, E edit, S skip, R regenerate, N never contact. Stop at the day's cap.",
  },
  { time: "Evening (10 min)", text: "Update the tracker, reply promptly, approve single follow-ups." },
];

const FUNNEL = [
  { label: "Collected", value: 0 },
  { label: "Qualified", value: 0 },
  { label: "Drafted", value: 0 },
  { label: "Sent", value: 0 },
  { label: "Replied", value: 0 },
];

export default function DashboardPage() {
  const [items, setItems] = React.useState<OnboardingItem[] | null>(null);

  const load = React.useCallback(() => {
    api<OnboardingItem[]>("/api/onboarding")
      .then(setItems)
      .catch(() => setItems([]));
  }, []);

  React.useEffect(load, [load]);

  async function toggle(item: OnboardingItem, done: boolean) {
    setItems((prev) =>
      prev ? prev.map((i) => (i.key === item.key ? { ...i, done } : i)) : prev
    );
    try {
      await api(`/api/onboarding/${item.key}`, { method: "PATCH", body: { done } });
    } finally {
      load();
    }
  }

  const doneCount = items?.filter((i) => i.done).length ?? 0;
  const total = items?.length ?? 5;
  const checklistDone = items !== null && doneCount === total;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-slate-900 dark:text-slate-100">
          Dashboard
        </h1>
        <p className="text-sm text-slate-500 dark:text-slate-400">
          Today&apos;s progress toward your daily targets.
        </p>
      </div>

      {!checklistDone && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle>First-run checklist</CardTitle>
                <CardDescription>
                  {doneCount} of {total} done. About 30 minutes of one-time setup.
                </CardDescription>
              </div>
              <Badge variant={checklistDone ? "success" : "secondary"}>
                {Math.round((doneCount / total) * 100)}%
              </Badge>
            </div>
          </CardHeader>
          <CardContent className="space-y-1">
            <Progress value={(doneCount / total) * 100} />
            <ul className="mt-3 space-y-1">
              {(items ?? []).map((item) => (
                <li
                  key={item.key}
                  className="flex items-center gap-3 rounded-md px-2 py-2 transition-colors hover:bg-slate-100/80 dark:hover:bg-slate-800/60"
                >
                  <Checkbox
                    checked={item.done}
                    disabled={item.auto}
                    onCheckedChange={(v) => toggle(item, v === true)}
                    aria-label={item.label}
                  />
                  <span
                    className={`flex-1 text-sm ${
                      item.done
                        ? "text-slate-400 dark:text-slate-500 line-through"
                        : "text-slate-700 dark:text-slate-200"
                    }`}
                  >
                    {item.auto && item.done ? (
                      <Check className="mr-1.5 inline h-3.5 w-3.5 text-emerald-600 dark:text-emerald-400" />
                    ) : item.auto ? (
                      <CircleDashed className="mr-1.5 inline h-3.5 w-3.5 text-slate-400 dark:text-slate-500" />
                    ) : null}
                    {item.label}
                  </span>
                  <Link
                    href={item.href}
                    className="text-xs font-medium text-slate-500 underline-offset-4 hover:underline dark:text-slate-400 dark:hover:text-slate-200"
                  >
                    open
                  </Link>
                </li>
              ))}
            </ul>
            <div className="pt-2">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => api("/api/onboarding/reset", { method: "POST" }).then(load)}
              >
                <RefreshCw /> Reset manual items
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle>Daily routine</CardTitle>
            <CardDescription>About 45 minutes a day.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {ROUTINE.map((r) => (
              <div key={r.time} className="text-sm">
                <div className="font-medium text-slate-800 dark:text-slate-100">{r.time}</div>
                <div className="text-slate-500 dark:text-slate-400">{r.text}</div>
              </div>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Today&apos;s funnel</CardTitle>
            <CardDescription>Live counts land here from step 2 onward.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            {FUNNEL.map((f) => (
              <div key={f.label} className="flex items-center justify-between text-sm">
                <span className="text-slate-600 dark:text-slate-300">{f.label}</span>
                <span className="font-medium tabular-nums text-slate-900 dark:text-slate-100">
                  {f.value}
                </span>
              </div>
            ))}
            <p className="pt-2 text-xs text-slate-400 dark:text-slate-500">
              Targets: collect 300+, qualify 100+, queue 50 drafts, send 30-40.
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Warm-up &amp; caps</CardTitle>
            <CardDescription>Protects your sending reputation.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <div className="flex items-center justify-between">
              <span className="text-slate-600 dark:text-slate-300">Emails today</span>
              <span className="font-medium tabular-nums text-slate-900 dark:text-slate-100">
                0 / 10
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-slate-600 dark:text-slate-300">Platform messages</span>
              <span className="font-medium tabular-nums text-slate-900 dark:text-slate-100">
                0 / 10
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-slate-600 dark:text-slate-300">Follow-ups due</span>
              <span className="font-medium tabular-nums text-slate-900 dark:text-slate-100">
                0
              </span>
            </div>
            <p className="pt-1 text-xs text-slate-400 dark:text-slate-500">
              Days 1-3: max 10 emails/day. The app pauses itself if bounce rate passes 5%.
            </p>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Reply rate by source</CardTitle>
            <CardDescription>Populates after your first sends.</CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-slate-500 dark:text-slate-400">
              Typical cold outreach reply rate is 3-8%. Under 2% after two weeks means the
              drafts need to be more specific, not that you need to send more.
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Next up</CardTitle>
            <CardDescription>Where the app is in its build order.</CardDescription>
          </CardHeader>
          <CardContent>
            <ol className="list-decimal space-y-1 pl-5 text-sm text-slate-600 dark:text-slate-300">
              <li>Monorepo, DB, auth, Profile, checklist (you are here)</li>
              <li>Collectors + Leads and Sources pages</li>
              <li>Dedupe and scoring</li>
              <li>Enrichment, drafting, self-check</li>
              <li>Review Queue + Gmail send</li>
            </ol>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
