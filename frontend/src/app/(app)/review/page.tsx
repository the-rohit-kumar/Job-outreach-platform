"use client";

import * as React from "react";
import Link from "next/link";
import {
  AlertCircle,
  ArrowRight,
  Check,
  CheckCircle2,
  Copy,
  ExternalLink,
  Keyboard,
  Mail,
  RefreshCw,
  Send,
  SkipForward,
  Sparkles,
  Trash2,
  UserCheck,
} from "lucide-react";
import { api } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

type ReviewResponse = {
  draft: Record<string, any>;
  lead: Record<string, any>;
  index: number;
  queue_size: number;
  variants: Array<{ id: number; variant: string; status: string }>;
};

type ReviewStats = {
  pending: number;
  needs_manual: number;
  reviewed_today: number;
};

export default function ReviewPage() {
  const [data, setData] = React.useState<ReviewResponse | null>(null);
  const [stats, setStats] = React.useState<ReviewStats>({ pending: 0, needs_manual: 0, reviewed_today: 0 });
  const [subject, setSubject] = React.useState("");
  const [body, setBody] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [copied, setCopied] = React.useState(false);
  const [feedback, setFeedback] = React.useState<{ type: "ok" | "err" | "info"; text: string } | null>(null);

  const textareaRef = React.useRef<HTMLTextAreaElement>(null);

  const loadNext = React.useCallback(async () => {
    setBusy(true);
    setFeedback(null);
    try {
      const [nextItem, statsData] = await Promise.all([
        api<ReviewResponse>("/api/review/next"),
        api<ReviewStats>("/api/review/stats"),
      ]);
      setData(nextItem);
      setStats(statsData);
      if (nextItem.draft && nextItem.draft.id) {
        setSubject(nextItem.draft.subject || "");
        setBody(nextItem.draft.body || "");
      } else {
        setSubject("");
        setBody("");
      }
    } catch (err: any) {
      setFeedback({ type: "err", text: err.message || "Failed to load review queue" });
    } finally {
      setBusy(false);
    }
  }, []);

  React.useEffect(() => {
    loadNext();
  }, [loadNext]);

  const handleAction = async (action: "approve" | "skip" | "never_contact" | "regenerate") => {
    if (!data?.draft?.id || busy) return;
    setBusy(true);
    setFeedback(null);
    try {
      const res = await api<{ ok: boolean; blocked?: string; reasons?: string[]; message?: string }>(
        `/api/review/${data.draft.id}/action`,
        {
          method: "POST",
          body: JSON.stringify({
            action,
            subject: data.draft.channel === "email" ? subject : undefined,
            body,
          }),
        }
      );

      if (!res.ok && res.blocked) {
        setFeedback({
          type: "err",
          text: `Action blocked: ${res.blocked} ${res.reasons ? `(${res.reasons.join("; ")})` : ""}`,
        });
        setBusy(false);
        return;
      }

      setFeedback({
        type: "ok",
        text: res.message || `Draft ${action}d successfully.`,
      });
      await loadNext();
    } catch (err: any) {
      setFeedback({ type: "err", text: err.message || `Failed to ${action} draft` });
      setBusy(false);
    }
  };

  const handleCopy = () => {
    if (!body) return;
    navigator.clipboard.writeText(body);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  // Keyboard hotkeys
  React.useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Don't trigger shortcuts if user is typing in an input or textarea
      const target = e.target as HTMLElement;
      if (target.tagName === "INPUT" || target.tagName === "TEXTAREA") {
        if (e.key === "Escape") {
          target.blur();
        }
        return;
      }

      if (e.key.toLowerCase() === "a") {
        e.preventDefault();
        handleAction("approve");
      } else if (e.key.toLowerCase() === "e") {
        e.preventDefault();
        textareaRef.current?.focus();
      } else if (e.key.toLowerCase() === "s") {
        e.preventDefault();
        handleAction("skip");
      } else if (e.key.toLowerCase() === "r") {
        e.preventDefault();
        handleAction("regenerate");
      } else if (e.key.toLowerCase() === "n") {
        e.preventDefault();
        handleAction("never_contact");
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  });

  const lead = data?.lead || {};
  const draft = data?.draft || {};
  const hasItem = Boolean(draft && draft.id);

  const wordCount = body ? body.trim().split(/\s+/).length : 0;
  const charCount = body ? body.length : 0;

  return (
    <div className="space-y-6">
      {/* Top Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between border-b border-slate-200 dark:border-slate-800 pb-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-slate-100">
              Review Queue
            </h1>
            {hasItem && (
              <Badge variant="outline" className="text-sm font-semibold text-emerald-600 dark:text-emerald-400">
                {data?.queue_size} pending
              </Badge>
            )}
          </div>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            Review and approve personalized founder drafts one by one before anything is dispatched.
          </p>
        </div>

        {/* Stats and hotkey indicators */}
        <div className="flex flex-wrap items-center gap-3 text-xs">
          <div className="flex items-center gap-2 rounded-lg bg-slate-100 dark:bg-slate-800 px-3 py-1.5 text-slate-700 dark:text-slate-300">
            <CheckCircle2 className="h-4 w-4 text-emerald-500" />
            <span>Reviewed today: <strong>{stats.reviewed_today}</strong></span>
          </div>
          {stats.needs_manual > 0 && (
            <div className="flex items-center gap-2 rounded-lg bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-800 px-3 py-1.5 text-amber-700 dark:text-amber-300">
              <AlertCircle className="h-4 w-4 text-amber-500" />
              <span>Needs manual: <strong>{stats.needs_manual}</strong></span>
            </div>
          )}
          <div className="hidden lg:flex items-center gap-2 rounded-lg border border-slate-200 dark:border-slate-800 px-3 py-1.5 text-slate-500 dark:text-slate-400">
            <Keyboard className="h-3.5 w-3.5" />
            <span>Hotkeys: <kbd className="font-mono font-semibold">A</kbd> Approve · <kbd className="font-mono font-semibold">E</kbd> Edit · <kbd className="font-mono font-semibold">S</kbd> Skip · <kbd className="font-mono font-semibold">R</kbd> Regen · <kbd className="font-mono font-semibold">N</kbd> Never</span>
          </div>
        </div>
      </div>

      {feedback && (
        <div
          className={`p-3.5 rounded-lg text-sm flex items-center justify-between ${
            feedback.type === "ok"
              ? "bg-emerald-50 text-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800"
              : "bg-red-50 text-red-800 dark:bg-red-950/50 dark:text-red-300 border border-red-200 dark:border-red-800"
          }`}
        >
          <span>{feedback.text}</span>
          <Button variant="ghost" size="sm" onClick={() => setFeedback(null)} className="h-6 px-2 text-xs">
            Dismiss
          </Button>
        </div>
      )}

      {/* Main Review Area or Empty State */}
      {!hasItem ? (
        <Card className="text-center py-16 px-6 max-w-2xl mx-auto shadow-sm">
          <CardContent className="space-y-4">
            <div className="mx-auto w-12 h-12 rounded-full bg-emerald-100 dark:bg-emerald-950/60 flex items-center justify-center text-emerald-600 dark:text-emerald-400">
              <Sparkles className="h-6 w-6" />
            </div>
            <CardTitle className="text-xl">Queue is clear!</CardTitle>
            <CardDescription className="text-slate-600 dark:text-slate-400 max-w-md mx-auto">
              There are no pending drafts awaiting approval right now. Run enabled collectors to discover more founders, or check your existing leads.
            </CardDescription>
            <div className="flex justify-center gap-3 pt-4">
              <Button asChild variant="outline">
                <Link href="/sources">Manage Sources</Link>
              </Button>
              <Button asChild>
                <Link href="/leads">
                  View Leads <ArrowRight className="ml-1 h-4 w-4" />
                </Link>
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          {/* Left Column: Target & Founder Context */}
          <div className="lg:col-span-5 space-y-4">
            <Card className="shadow-sm">
              <CardHeader className="pb-3">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <CardTitle className="text-lg font-bold text-slate-900 dark:text-slate-100">
                      {lead.company || "Target Company"}
                    </CardTitle>
                    <p className="text-sm text-slate-600 dark:text-slate-400 font-medium">
                      {lead.title}
                    </p>
                  </div>
                  {lead.score !== undefined && (
                    <Badge
                      className={`text-xs px-2.5 py-1 ${
                        lead.score >= 70
                          ? "bg-emerald-500 text-white"
                          : lead.score >= 55
                          ? "bg-amber-500 text-white"
                          : "bg-slate-500 text-white"
                      }`}
                    >
                      {lead.score} pts
                    </Badge>
                  )}
                </div>
                {lead.score_reason && (
                  <p className="text-xs text-slate-500 dark:text-slate-400 italic mt-1">
                    "{lead.score_reason}"
                  </p>
                )}
              </CardHeader>

              <CardContent className="space-y-4 text-sm">
                {/* Contact and Email Row */}
                <div className="rounded-lg bg-slate-50 dark:bg-slate-900/60 p-3.5 space-y-2 border border-slate-200/60 dark:border-slate-800">
                  <div className="flex items-center justify-between text-xs text-slate-500 dark:text-slate-400">
                    <span className="font-semibold uppercase tracking-wider">Contact / Recipient</span>
                    {lead.channel === "email" ? (
                      <Badge variant="secondary" className="gap-1 text-[11px] text-blue-600 dark:text-blue-400">
                        <Mail className="h-3 w-3" /> Direct Email
                      </Badge>
                    ) : (
                      <Badge variant="outline" className="text-[11px]">
                        Platform ({lead.source})
                      </Badge>
                    )}
                  </div>
                  <div className="flex items-center justify-between font-medium">
                    <div className="flex items-center gap-1.5 text-slate-900 dark:text-slate-100">
                      <UserCheck className="h-4 w-4 text-emerald-500" />
                      <span>{lead.contact?.name || "Hiring Lead / Founder"}</span>
                      {lead.contact?.role && (
                        <span className="text-xs text-slate-500">({lead.contact.role})</span>
                      )}
                    </div>
                    {lead.contact?.email ? (
                      <a
                        href={`mailto:${lead.contact.email}`}
                        className="text-xs text-blue-600 dark:text-blue-400 hover:underline flex items-center gap-1"
                      >
                        {lead.contact.email}
                      </a>
                    ) : (
                      <span className="text-xs text-slate-400">No public email</span>
                    )}
                  </div>
                </div>

                {/* Specific Hook */}
                {lead.hook && (
                  <div className="space-y-1.5">
                    <Label className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">
                      Identified Hook / Signal
                    </Label>
                    <div className="p-3 rounded-lg bg-amber-50/60 dark:bg-amber-950/20 border border-amber-200/60 dark:border-amber-900/50 text-amber-900 dark:text-amber-200 text-xs leading-relaxed">
                      "{lead.hook}"
                    </div>
                  </div>
                )}

                {/* Additional Metadata */}
                <div className="grid grid-cols-2 gap-2 text-xs pt-1 border-t border-slate-100 dark:border-slate-800">
                  <div>
                    <span className="text-slate-400 block">Location & Type</span>
                    <span className="text-slate-700 dark:text-slate-300 font-medium">
                      {lead.location || "Remote"} {lead.remote ? "• Remote" : ""}
                    </span>
                  </div>
                  <div>
                    <span className="text-slate-400 block">Source</span>
                    <span className="text-slate-700 dark:text-slate-300 font-medium capitalize">
                      {lead.source}
                    </span>
                  </div>
                </div>

                {/* Source URL link */}
                {lead.url && (
                  <div className="pt-2">
                    <a
                      href={lead.url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-xs text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-100 flex items-center gap-1.5"
                    >
                      <ExternalLink className="h-3.5 w-3.5" />
                      <span>View original post / website</span>
                    </a>
                  </div>
                )}

                {/* Posting preview snippet */}
                {lead.description && (
                  <div className="space-y-1.5 pt-2">
                    <Label className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">
                      Posting Text
                    </Label>
                    <div className="max-h-36 overflow-y-auto p-2.5 rounded bg-slate-50 dark:bg-slate-900 text-xs text-slate-600 dark:text-slate-400 leading-relaxed font-mono whitespace-pre-wrap">
                      {lead.description}
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>

          {/* Right Column: Draft Editor & Actions */}
          <div className="lg:col-span-7 space-y-4">
            <Card className="shadow-sm border-slate-200 dark:border-slate-800">
              <CardHeader className="pb-3 border-b border-slate-100 dark:border-slate-800">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Badge variant="outline" className="font-semibold uppercase tracking-wider text-xs">
                      {draft.variant || "Email"}
                    </Badge>
                    <span className="text-xs text-slate-500">
                      Gen #{draft.generation || 1} • Model: {draft.model || "heuristic"}
                    </span>
                  </div>
                  <div className="flex items-center gap-3 text-xs text-slate-500">
                    <span>
                      {wordCount} words / {charCount} chars
                    </span>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={handleCopy}
                      className="h-7 px-2.5 text-xs gap-1"
                    >
                      {copied ? <Check className="h-3.5 w-3.5 text-emerald-500" /> : <Copy className="h-3.5 w-3.5" />}
                      {copied ? "Copied" : "Copy"}
                    </Button>
                  </div>
                </div>
              </CardHeader>

              <CardContent className="space-y-4 pt-4">
                {/* Subject Line for Email */}
                {draft.channel === "email" && (
                  <div className="space-y-1.5">
                    <Label htmlFor="subject" className="text-xs font-semibold text-slate-600 dark:text-slate-300">
                      Subject Line
                    </Label>
                    <Input
                      id="subject"
                      value={subject}
                      onChange={(e) => setSubject(e.target.value)}
                      placeholder="Email subject..."
                      className="font-medium"
                    />
                  </div>
                )}

                {/* Body Textarea */}
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between">
                    <Label htmlFor="body" className="text-xs font-semibold text-slate-600 dark:text-slate-300">
                      Personalized Message Body
                    </Label>
                    <span className="text-[11px] text-slate-400">
                      Press <kbd className="font-mono font-semibold">E</kbd> to edit
                    </span>
                  </div>
                  <Textarea
                    ref={textareaRef}
                    id="body"
                    rows={11}
                    value={body}
                    onChange={(e) => setBody(e.target.value)}
                    className="font-sans text-sm leading-relaxed p-3.5 focus-visible:ring-1"
                    placeholder="Draft message body..."
                  />
                </div>

                {/* Checks Status */}
                {draft.fail_reason ? (
                  <div className="rounded-lg bg-red-50 dark:bg-red-950/40 p-3 border border-red-200 dark:border-red-900 text-xs text-red-700 dark:text-red-300 flex items-center gap-2">
                    <AlertCircle className="h-4 w-4 text-red-500 flex-shrink-0" />
                    <span>Check failure: {draft.fail_reason}</span>
                  </div>
                ) : (
                  <div className="rounded-lg bg-emerald-50/50 dark:bg-emerald-950/20 p-2.5 border border-emerald-200/50 dark:border-emerald-900/40 text-xs text-emerald-700 dark:text-emerald-300 flex items-center gap-2">
                    <CheckCircle2 className="h-4 w-4 text-emerald-500 flex-shrink-0" />
                    <span>Passes safety rules: specific hook referenced, proof of work included, opt-out line attached.</span>
                  </div>
                )}

                {/* Primary Action Buttons */}
                <div className="flex flex-wrap items-center justify-between gap-3 pt-3 border-t border-slate-100 dark:border-slate-800">
                  <div className="flex items-center gap-2">
                    <Button
                      variant="destructive"
                      size="sm"
                      disabled={busy}
                      onClick={() => handleAction("never_contact")}
                      className="h-9 gap-1.5 text-xs"
                      title="Permanently suppress this lead"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                      Never Contact <kbd className="ml-1 opacity-75 font-mono">N</kbd>
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={busy}
                      onClick={() => handleAction("skip")}
                      className="h-9 gap-1.5 text-xs text-slate-600 dark:text-slate-300"
                    >
                      <SkipForward className="h-3.5 w-3.5" />
                      Skip <kbd className="ml-1 opacity-75 font-mono">S</kbd>
                    </Button>
                  </div>

                  <div className="flex items-center gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={busy}
                      onClick={() => handleAction("regenerate")}
                      className="h-9 gap-1.5 text-xs"
                    >
                      <RefreshCw className="h-3.5 w-3.5" />
                      Regenerate <kbd className="ml-1 opacity-75 font-mono">R</kbd>
                    </Button>
                    <Button
                      size="sm"
                      disabled={busy}
                      onClick={() => handleAction("approve")}
                      className="h-9 gap-1.5 text-xs bg-emerald-600 hover:bg-emerald-700 text-white font-semibold px-4"
                    >
                      <Send className="h-3.5 w-3.5" />
                      Approve & Queue <kbd className="ml-1.5 opacity-90 font-mono text-[11px]">A</kbd>
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      )}
    </div>
  );
}
