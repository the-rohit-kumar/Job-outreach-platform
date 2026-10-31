"use client";

import * as React from "react";
import {
  AlertCircle,
  CheckCircle2,
  Clock,
  History,
  Play,
  Plug,
  RefreshCw,
  Sliders,
  Sparkles,
} from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { Source, SourceRun } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { TagEditor } from "@/components/tag-editor";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

export default function SourcesPage() {
  const [sources, setSources] = React.useState<Source[] | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [runningKey, setRunningKey] = React.useState<string | null>(null);
  const [editSource, setEditSource] = React.useState<Source | null>(null);
  const [historySource, setHistorySource] = React.useState<Source | null>(null);
  const [runs, setRuns] = React.useState<SourceRun[] | null>(null);
  const [feedback, setFeedback] = React.useState<string | null>(null);

  const loadSources = React.useCallback(() => {
    api<Source[]>("/api/sources")
      .then((data) => {
        setSources(data);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  React.useEffect(() => {
    loadSources();
  }, [loadSources]);

  async function toggleSource(src: Source, enabled: boolean) {
    setSources((prev) =>
      prev ? prev.map((s) => (s.key === src.key ? { ...s, enabled } : s)) : prev
    );
    try {
      const updated = await api<Source>(`/api/sources/${src.key}`, {
        method: "PATCH",
        body: { enabled },
      });
      setSources((prev) =>
        prev ? prev.map((s) => (s.key === src.key ? updated : s)) : prev
      );
    } catch (e) {
      loadSources();
    }
  }

  async function handleRunNow(src: Source) {
    setRunningKey(src.key);
    setFeedback(null);
    try {
      const res = await api<{
        found: number;
        new: number;
        duplicates: number;
        suppressed: number;
        status: string;
        error: string;
      }>(`/api/sources/${src.key}/run`, { method: "POST" });
      setFeedback(
        `${src.name}: ${res.status === "ok" ? "Success" : res.status}. Found ${res.found} leads (${res.new} new, ${res.duplicates} duplicates).`
      );
      loadSources();
    } catch (err) {
      setFeedback(
        `${src.name} run failed: ${err instanceof ApiError ? err.message : "Error"}`
      );
    } finally {
      setRunningKey(null);
    }
  }

  async function openHistory(src: Source) {
    setHistorySource(src);
    setRuns(null);
    try {
      const data = await api<SourceRun[]>(`/api/sources/${src.key}/runs`);
      setRuns(data);
    } catch {
      setRuns([]);
    }
  }

  async function saveConfig() {
    if (!editSource) return;
    try {
      const updated = await api<Source>(`/api/sources/${editSource.key}`, {
        method: "PATCH",
        body: {
          config: editSource.config,
          keywords: editSource.config.keywords ?? [],
        },
      });
      setSources((prev) =>
        prev ? prev.map((s) => (s.key === editSource.key ? updated : s)) : prev
      );
      setEditSource(null);
    } catch {
      // error handled
    }
  }

  const enabledCount = sources?.filter((s) => s.enabled).length ?? 0;
  const totalCount = sources?.length ?? 0;

  return (
    <div className="space-y-6">
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-slate-900 dark:text-slate-100">
            Sources &amp; Collectors
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400">
            Manage legitimate job boards, RSS feeds, and developer community sources.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Badge variant="outline" className="px-3 py-1 text-sm font-medium">
            {enabledCount} of {totalCount} active
          </Badge>
          <Button variant="outline" size="sm" onClick={loadSources} disabled={loading}>
            <RefreshCw className={loading ? "animate-spin" : ""} /> Refresh
          </Button>
        </div>
      </div>

      {feedback && (
        <div className="flex items-center justify-between rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-900 dark:border-emerald-800/40 dark:bg-emerald-950/40 dark:text-emerald-200">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-600 dark:text-emerald-400" />
            <span>{feedback}</span>
          </div>
          <button
            type="button"
            className="text-xs font-semibold text-emerald-700 hover:underline dark:text-emerald-300"
            onClick={() => setFeedback(null)}
          >
            Dismiss
          </button>
        </div>
      )}

      {loading && !sources ? (
        <div className="py-12 text-center text-sm text-slate-500 dark:text-slate-400">
          Loading collectors…
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {sources?.map((src) => {
            const isRunning = runningKey === src.key;
            const keywords: string[] = src.config?.keywords ?? [];
            const queries: string[] = src.config?.queries ?? [];
            const feeds: string[] = src.config?.feeds ?? [];

            return (
              <Card
                key={src.key}
                className={`transition-all duration-200 ${
                  src.enabled
                    ? "border-slate-300 shadow-xs dark:border-slate-700"
                    : "opacity-80"
                }`}
              >
                <CardHeader className="pb-3">
                  <div className="flex items-start justify-between gap-4">
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <CardTitle className="text-base font-semibold">
                          {src.name}
                        </CardTitle>
                        <Badge variant="secondary" className="text-[11px] uppercase tracking-wide">
                          {src.kind}
                        </Badge>
                      </div>
                      <CardDescription className="text-xs">
                        Key: <code className="text-slate-700 dark:text-slate-300">{src.key}</code>
                      </CardDescription>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-medium text-slate-500 dark:text-slate-400">
                        {src.enabled ? "Enabled" : "Disabled"}
                      </span>
                      <Switch
                        checked={src.enabled}
                        onCheckedChange={(val) => toggleSource(src, val)}
                        aria-label={`Toggle ${src.name}`}
                      />
                    </div>
                  </div>
                </CardHeader>

                <CardContent className="space-y-4 pt-1">
                  {/* Status & Counts */}
                  <div className="grid grid-cols-2 gap-3 rounded-lg border border-slate-100 bg-slate-50/70 p-3 text-xs dark:border-slate-800 dark:bg-slate-900/50">
                    <div>
                      <div className="text-slate-500 dark:text-slate-400">Last run</div>
                      <div className="mt-0.5 font-medium text-slate-800 dark:text-slate-200">
                        {src.last_run_at ? (
                          new Date(src.last_run_at).toLocaleString(undefined, {
                            month: "short",
                            day: "numeric",
                            hour: "2-digit",
                            minute: "2-digit",
                          })
                        ) : (
                          <span className="text-slate-400">Never run</span>
                        )}
                      </div>
                    </div>
                    <div>
                      <div className="text-slate-500 dark:text-slate-400">Last result</div>
                      <div className="mt-0.5 flex items-center gap-1.5 font-medium">
                        {src.last_status === "ok" && (
                          <Badge variant="success" className="px-1.5 py-0 text-[10px]">
                            OK ({src.last_count} leads)
                          </Badge>
                        )}
                        {src.last_status === "error" && (
                          <Badge variant="destructive" className="px-1.5 py-0 text-[10px]">
                            Error
                          </Badge>
                        )}
                        {!src.last_status && (
                          <span className="text-slate-400 dark:text-slate-500">—</span>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Error Callout */}
                  {src.last_error && (
                    <div className="flex items-start gap-2 rounded-md border border-red-200 bg-red-50 p-2.5 text-xs text-red-800 dark:border-red-900/40 dark:bg-red-950/40 dark:text-red-300">
                      <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-red-600 dark:text-red-400" />
                      <div className="line-clamp-2">{src.last_error}</div>
                    </div>
                  )}

                  {/* Tags Preview */}
                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between text-xs text-slate-500 dark:text-slate-400">
                      <span>Keywords ({keywords.length || queries.length || feeds.length})</span>
                      <button
                        type="button"
                        onClick={() => setEditSource(src)}
                        className="text-xs font-medium text-slate-700 underline-offset-4 hover:underline dark:text-slate-300 cursor-pointer"
                      >
                        Edit filters
                      </button>
                    </div>
                    <div className="flex flex-wrap gap-1">
                      {(keywords.length > 0 ? keywords : queries).slice(0, 5).map((kw) => (
                        <span
                          key={kw}
                          className="rounded-md bg-slate-100 px-2 py-0.5 text-[11px] text-slate-700 dark:bg-slate-800 dark:text-slate-300"
                        >
                          {kw}
                        </span>
                      ))}
                      {(keywords.length > 5 || queries.length > 5) && (
                        <span className="rounded-md bg-slate-100 px-1.5 py-0.5 text-[10px] text-slate-500 dark:bg-slate-800 dark:text-slate-400">
                          +{Math.max(keywords.length, queries.length) - 5} more
                        </span>
                      )}
                      {keywords.length === 0 && queries.length === 0 && feeds.length > 0 && (
                        <span className="text-[11px] text-slate-500 dark:text-slate-400">
                          {feeds.length} custom RSS feed URLs configured
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Actions */}
                  <div className="flex items-center justify-between border-t border-slate-100 pt-3 dark:border-slate-800">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => openHistory(src)}
                      className="text-xs"
                    >
                      <History className="h-3.5 w-3.5" /> Runs history
                    </Button>
                    <Button
                      size="sm"
                      onClick={() => handleRunNow(src)}
                      disabled={isRunning || !src.enabled}
                    >
                      {isRunning ? (
                        <>
                          <RefreshCw className="h-3.5 w-3.5 animate-spin" /> Running…
                        </>
                      ) : (
                        <>
                          <Play className="h-3.5 w-3.5" /> Run now
                        </>
                      )}
                    </Button>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

      {/* Edit Config Modal */}
      {editSource && (
        <Dialog open={true} onOpenChange={(open) => !open && setEditSource(null)}>
          <DialogContent className="sm:max-w-md">
            <DialogHeader>
              <DialogTitle>Configure {editSource.name}</DialogTitle>
              <DialogDescription>
                Customize targeting keywords and queries for this collector.
              </DialogDescription>
            </DialogHeader>

            <div className="space-y-4 py-2">
              <div className="space-y-2">
                <label className="text-sm font-medium text-slate-800 dark:text-slate-200">
                  Target Keywords
                </label>
                <p className="text-xs text-slate-500 dark:text-slate-400">
                  Only postings matching one of these terms will be saved as leads.
                </p>
                <TagEditor
                  values={editSource.config.keywords ?? []}
                  onChange={(next) =>
                    setEditSource({
                      ...editSource,
                      config: { ...editSource.config, keywords: next },
                    })
                  }
                  placeholder="e.g. langchain, rag, agents"
                />
              </div>

              {editSource.config.queries !== undefined && (
                <div className="space-y-2">
                  <label className="text-sm font-medium text-slate-800 dark:text-slate-200">
                    Search Queries
                  </label>
                  <TagEditor
                    values={editSource.config.queries ?? []}
                    onChange={(next) =>
                      setEditSource({
                        ...editSource,
                        config: { ...editSource.config, queries: next },
                      })
                    }
                    placeholder="e.g. llm evaluation, mcp server"
                  />
                </div>
              )}
            </div>

            <div className="flex justify-end gap-2 pt-2">
              <Button variant="outline" onClick={() => setEditSource(null)}>
                Cancel
              </Button>
              <Button onClick={saveConfig}>Save filters</Button>
            </div>
          </DialogContent>
        </Dialog>
      )}

      {/* Run History Modal */}
      {historySource && (
        <Dialog open={true} onOpenChange={(open) => !open && setHistorySource(null)}>
          <DialogContent className="max-w-2xl">
            <DialogHeader>
              <DialogTitle>{historySource.name} — Run History</DialogTitle>
              <DialogDescription>
                Recent execution runs, duration, and lead outcomes.
              </DialogDescription>
            </DialogHeader>

            <div className="max-h-96 overflow-y-auto">
              {!runs ? (
                <div className="py-8 text-center text-sm text-slate-500">Loading history…</div>
              ) : runs.length === 0 ? (
                <div className="py-8 text-center text-sm text-slate-500">No runs recorded yet.</div>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Time</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead className="text-right">Found</TableHead>
                      <TableHead className="text-right">New</TableHead>
                      <TableHead>Details</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {runs.map((r) => (
                      <TableRow key={r.id}>
                        <TableCell className="font-mono text-xs">
                          {new Date(r.started_at).toLocaleTimeString([], {
                            hour: "2-digit",
                            minute: "2-digit",
                            second: "2-digit",
                          })}
                        </TableCell>
                        <TableCell>
                          <Badge
                            variant={
                              r.status === "ok"
                                ? "success"
                                : r.status === "running"
                                ? "secondary"
                                : "destructive"
                            }
                            className="text-[10px]"
                          >
                            {r.status}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-right font-medium tabular-nums">
                          {r.leads_found}
                        </TableCell>
                        <TableCell className="text-right font-semibold tabular-nums text-emerald-600 dark:text-emerald-400">
                          +{r.leads_new}
                        </TableCell>
                        <TableCell className="max-w-[200px] truncate text-xs text-slate-500 dark:text-slate-400">
                          {r.error || "Completed cleanly"}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </div>

            <div className="flex justify-end pt-2">
              <Button variant="outline" onClick={() => setHistorySource(null)}>
                Close
              </Button>
            </div>
          </DialogContent>
        </Dialog>
      )}
    </div>
  );
}
