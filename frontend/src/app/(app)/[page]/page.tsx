import { notFound } from "next/navigation";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

const PAGES: Record<string, { title: string; step: number; body: string; bullets: string[] }> = {
  sources: {
    title: "Sources",
    step: 2,
    body: "Toggle each collector, set keywords and company slug lists, see last-run status and errors, run a source on demand.",
    bullets: [
      "Honor robots.txt, terms and rate limits on every collector",
      "API and RSS feeds first, manual import for the rest",
      "Fails gracefully: one dead source never stops the pipeline",
    ],
  },
  leads: {
    title: "Leads",
    step: 2,
    body: "Filterable table of everything collected: score, source, remote, type, date, status and channel, with bulk actions and a lead drawer.",
    bullets: [
      "Posting text, company context and public contact info",
      "Full history: collected, scored, drafted, sent, replied",
      "Suppression and 'never contact' respected everywhere",
    ],
  },
  review: {
    title: "Review Queue",
    step: 5,
    body: "One draft at a time: lead summary on the left, editable message on the right. A approve, E edit, S skip, R regenerate, N never contact.",
    bullets: [
      "Email drafts: approve and send through the Gmail API",
      "Platform drafts: copy or fill through the extension, you press Send",
      "Target: 40 reviews in under 30 minutes",
    ],
  },
  tracker: {
    title: "Tracker",
    step: 6,
    body: "Kanban board of Drafted, Sent, Replied, Call, Trial task, Won and Closed, with notes and dates.",
    bullets: ["Reply detection through Gmail", "One follow-up after 7 days, then close", "Opt-outs honored instantly"],
  },
  analytics: {
    title: "Analytics",
    step: 8,
    body: "Reply rate and positive-reply rate by source, channel, variant and score band, plus a weekly summary of what is worth your time.",
    bullets: ["Double down on the top 2-3 sources", "Disable sources under 1% after 100+ messages"],
  },
  settings: {
    title: "Settings",
    step: 5,
    body: "Daily targets, warm-up schedule, send window, caps, Gmail connection and the suppression list.",
    bullets: ["Every setting carries a tooltip explaining the safe default", "Spend cap on LLM usage"],
  },
  help: {
    title: "Help",
    step: 8,
    body: "The full user manual rendered in-app with search: setup, daily routine, warm-up, extension, writing good messages.",
    bullets: ["Same content as USER_MANUAL.md at the repo root"],
  },
};

export default async function ComingSoonPage({
  params,
}: {
  params: Promise<{ page: string }>;
}) {
  const { page } = await params;
  const info = PAGES[page];
  if (!info) notFound();

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-slate-900 dark:text-slate-100">{info.title}</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400">{info.body}</p>
      </div>
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle>Arrives in build step {info.step}</CardTitle>
            <Badge variant="secondary">not built yet</Badge>
          </div>
          <CardDescription>
            The build order stops after each step so you can demo it before the next one starts.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ul className="list-disc space-y-1 pl-5 text-sm text-slate-600 dark:text-slate-300">
            {info.bullets.map((b) => (
              <li key={b}>{b}</li>
            ))}
          </ul>
        </CardContent>
      </Card>
    </div>
  );
}
