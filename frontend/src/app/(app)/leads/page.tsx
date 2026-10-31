"use client";

import * as React from "react";
import Link from "next/link";
import {
  ColumnDef,
  flexRender,
  getCoreRowModel,
  useReactTable,
} from "@tanstack/react-table";
import {
  AlertTriangle,
  ArrowUpDown,
  Ban,
  Check,
  CheckCircle,
  ExternalLink,
  Eye,
  Filter,
  Layers,
  Mail,
  MessageSquare,
  MoreHorizontal,
  RefreshCw,
  Search,
  Sparkles,
  UserCheck,
  X,
} from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { Lead, LeadDetail, LeadHistory, LeadsPageData } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

export default function LeadsPage() {
  const [data, setData] = React.useState<LeadsPageData | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [rowSelection, setRowSelection] = React.useState<Record<string, boolean>>({});

  // Filter & Search states
  const [search, setSearch] = React.useState("");
  const [sourceFilter, setSourceFilter] = React.useState<string>("all");
  const [statusFilter, setStatusFilter] = React.useState<string>("all");
  const [channelFilter, setChannelFilter] = React.useState<string>("all");
  const [minScore, setMinScore] = React.useState<string>("all");
  const [remoteOnly, setRemoteOnly] = React.useState<boolean>(false);
  const [page, setPage] = React.useState(1);
  const [pageSize] = React.useState(25);
  const [sortBy, setSortBy] = React.useState("created_at");
  const [sortOrder, setSortOrder] = React.useState<"asc" | "desc">("desc");

  // Selected lead for Drawer
  const [selectedLeadId, setSelectedLeadId] = React.useState<number | null>(null);
  const [leadDetail, setLeadDetail] = React.useState<LeadDetail | null>(null);
  const [leadHistory, setLeadHistory] = React.useState<LeadHistory | null>(null);
  const [detailLoading, setDetailLoading] = React.useState(false);

  // Bulk action feedback
  const [actionFeedback, setActionFeedback] = React.useState<string | null>(null);
  const [busyAction, setBusyAction] = React.useState(false);

  const fetchLeads = React.useCallback(() => {
    setLoading(true);
    const params = new URLSearchParams();
    if (search.trim()) params.set("q", search.trim());
    if (sourceFilter !== "all") params.set("source", sourceFilter);
    if (statusFilter !== "all") params.set("status", statusFilter);
    if (channelFilter !== "all") params.set("channel", channelFilter);
    if (minScore !== "all") params.set("min_score", minScore);
    if (remoteOnly) params.set("remote", "true");
    params.set("page", String(page));
    params.set("page_size", String(pageSize));
    params.set("sort", sortBy);
    params.set("order", sortOrder);

    api<LeadsPageData>(`/api/leads?${params.toString()}`)
      .then((res) => {
        setData(res);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [search, sourceFilter, statusFilter, channelFilter, minScore, remoteOnly, page, pageSize, sortBy, sortOrder]);

  React.useEffect(() => {
    fetchLeads();
  }, [fetchLeads]);

  // Lead detail drawer
  React.useEffect(() => {
    if (!selectedLeadId) {
      setLeadDetail(null);
      setLeadHistory(null);
      return;
    }
    setDetailLoading(true);
    Promise.all([
      api<LeadDetail>(`/api/leads/${selectedLeadId}`),
      api<LeadHistory>(`/api/leads/${selectedLeadId}/history`),
    ])
      .then(([detail, history]) => {
        setLeadDetail(detail);
        setLeadHistory(history);
      })
      .catch(() => {})
      .finally(() => setDetailLoading(false));
  }, [selectedLeadId]);

  // Selected IDs from TanStack table selection
  const selectedIds = React.useMemo(() => {
    if (!data?.items) return [];
    return Object.keys(rowSelection)
      .filter((k) => rowSelection[k])
      .map((idx) => data.items[Number(idx)]?.id)
      .filter(Boolean);
  }, [rowSelection, data]);

  async function handleBulk(action: string) {
    if (selectedIds.length === 0) return;
    setBusyAction(true);
    try {
      const res = await api<{ changed: number; action: string }>("/api/leads/bulk", {
        method: "POST",
        body: { ids: selectedIds, action },
      });
      setActionFeedback(`Updated ${res.changed} lead(s) via ${action}.`);
      setRowSelection({});
      fetchLeads();
    } catch (err) {
      setActionFeedback(err instanceof ApiError ? err.message : "Bulk action failed");
    } finally {
      setBusyAction(false);
    }
  }

  async function handleDedupe() {
    setBusyAction(true);
    try {
      const res = await api<{ found_duplicates: number }>("/api/leads/dedupe", {
        method: "POST",
      });
      setActionFeedback(`Deduplication run finished. Marked ${res.found_duplicates} duplicates.`);
      fetchLeads();
    } catch {
      setActionFeedback("Dedupe run failed.");
    } finally {
      setBusyAction(false);
    }
  }

  // Column definitions for TanStack Table
  const columns = React.useMemo<ColumnDef<Lead>[]>(
    () => [
      {
        id: "select",
        header: ({ table }) => (
          <Checkbox
            checked={
              table.getIsAllPageRowsSelected() ||
              (table.getIsSomePageRowsSelected() && "indeterminate")
            }
            onCheckedChange={(value) => table.toggleAllPageRowsSelected(!!value)}
            aria-label="Select all"
          />
        ),
        cell: ({ row }) => (
          <Checkbox
            checked={row.getIsSelected()}
            onCheckedChange={(value) => row.toggleSelected(!!value)}
            aria-label="Select row"
          />
        ),
        enableSorting: false,
      },
      {
        accessorKey: "score",
        header: () => (
          <button
            type="button"
            onClick={() => {
              setSortBy("score");
              setSortOrder((prev) => (prev === "asc" ? "desc" : "asc"));
            }}
            className="flex items-center gap-1 font-semibold hover:text-slate-900 dark:hover:text-slate-100 cursor-pointer"
          >
            Score <ArrowUpDown className="h-3 w-3" />
          </button>
        ),
        cell: ({ row }) => {
          const score = row.original.score;
          if (score === null || score === undefined) {
            return (
              <Badge variant="outline" className="text-slate-400">
                Unscored
              </Badge>
            );
          }
          const variant =
            score >= 75 ? "success" : score >= 50 ? "warning" : "secondary";
          return (
            <Badge variant={variant} className="font-mono font-semibold">
              {score}
            </Badge>
          );
        },
      },
      {
        accessorKey: "title",
        header: "Opportunity & Company",
        cell: ({ row }) => {
          const l = row.original;
          return (
            <div className="max-w-md space-y-1">
              <button
                type="button"
                onClick={() => setSelectedLeadId(l.id)}
                className="text-left font-medium text-slate-900 hover:underline dark:text-slate-100 cursor-pointer line-clamp-1"
              >
                {l.title || "Untitled Opportunity"}
              </button>
              <div className="flex items-center gap-2 text-xs text-slate-500 dark:text-slate-400">
                <span className="font-medium text-slate-700 dark:text-slate-300">
                  {l.company || "Unknown Company"}
                </span>
                {l.location && <span>• {l.location}</span>}
                {l.remote && (
                  <Badge variant="secondary" className="px-1.5 py-0 text-[10px]">
                    Remote
                  </Badge>
                )}
              </div>
            </div>
          );
        },
      },
      {
        accessorKey: "source",
        header: "Source",
        cell: ({ row }) => (
          <Badge variant="outline" className="text-xs uppercase">
            {row.original.source}
          </Badge>
        ),
      },
      {
        accessorKey: "channel",
        header: "Channel",
        cell: ({ row }) => {
          const ch = row.original.channel;
          return (
            <div className="flex items-center gap-1.5 text-xs text-slate-600 dark:text-slate-400">
              {ch === "email" ? (
                <Mail className="h-3.5 w-3.5 text-indigo-500" />
              ) : (
                <MessageSquare className="h-3.5 w-3.5 text-emerald-500" />
              )}
              <span className="capitalize">{ch}</span>
            </div>
          );
        },
      },
      {
        accessorKey: "status",
        header: "Status",
        cell: ({ row }) => {
          const s = row.original.status;
          return (
            <Badge
              variant={
                s === "qualified"
                  ? "success"
                  : s === "drafted"
                  ? "default"
                  : s === "duplicate" || s === "suppressed"
                  ? "destructive"
                  : "secondary"
              }
              className="text-xs capitalize"
            >
              {s}
            </Badge>
          );
        },
      },
      {
        accessorKey: "created_at",
        header: () => (
          <button
            type="button"
            onClick={() => {
              setSortBy("created_at");
              setSortOrder((prev) => (prev === "asc" ? "desc" : "asc"));
            }}
            className="flex items-center gap-1 font-semibold hover:text-slate-900 dark:hover:text-slate-100 cursor-pointer"
          >
            Collected <ArrowUpDown className="h-3 w-3" />
          </button>
        ),
        cell: ({ row }) => (
          <span className="text-xs tabular-nums text-slate-500 dark:text-slate-400">
            {new Date(row.original.created_at).toLocaleDateString(undefined, {
              month: "short",
              day: "numeric",
            })}
          </span>
        ),
      },
      {
        id: "actions",
        header: "",
        cell: ({ row }) => (
          <div className="flex items-center justify-end gap-1">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setSelectedLeadId(row.original.id)}
              aria-label="Inspect lead"
            >
              <Eye className="h-3.5 w-3.5" />
            </Button>
            {row.original.url && (
              <Button variant="ghost" size="sm" asChild>
                <a
                  href={row.original.url}
                  target="_blank"
                  rel="noreferrer"
                  aria-label="Open original posting"
                >
                  <ExternalLink className="h-3.5 w-3.5 text-slate-400" />
                </a>
              </Button>
            )}
          </div>
        ),
      },
    ],
    []
  );

  const table = useReactTable({
    data: data?.items ?? [],
    columns,
    state: { rowSelection },
    enableRowSelection: true,
    onRowSelectionChange: setRowSelection,
    getCoreRowModel: getCoreRowModel(),
  });

  const totalPages = Math.ceil((data?.total ?? 0) / pageSize) || 1;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-slate-900 dark:text-slate-100">
            Leads
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400">
            All AI engineering leads collected across legitimate sources with automated scoring.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={handleDedupe} disabled={busyAction}>
            <Layers className="h-4 w-4" /> Run dedupe
          </Button>
          <Button variant="outline" size="sm" onClick={fetchLeads} disabled={loading}>
            <RefreshCw className={loading ? "animate-spin" : ""} /> Refresh
          </Button>
        </div>
      </div>

      {actionFeedback && (
        <div className="flex items-center justify-between rounded-lg border border-slate-200 bg-slate-50 px-4 py-2.5 text-sm text-slate-800 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-200">
          <span>{actionFeedback}</span>
          <button
            type="button"
            className="text-xs font-medium text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200"
            onClick={() => setActionFeedback(null)}
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Filter and Search Bar */}
      <Card>
        <CardContent className="p-4 space-y-3">
          <div className="flex flex-col gap-3 md:flex-row md:items-center">
            {/* Search Input */}
            <div className="relative flex-1">
              <Search className="absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
              <Input
                placeholder="Search title, company, skills, or hook…"
                value={search}
                onChange={(e) => {
                  setSearch(e.target.value);
                  setPage(1);
                }}
                className="pl-9"
              />
            </div>

            {/* Source Filter */}
            <div className="w-full md:w-40">
              <Select
                value={sourceFilter}
                onValueChange={(val) => {
                  setSourceFilter(val);
                  setPage(1);
                }}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Source" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All sources</SelectItem>
                  {data?.facets?.sources?.map((s) => (
                    <SelectItem key={s} value={s}>
                      {s.toUpperCase()}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Status Filter */}
            <div className="w-full md:w-36">
              <Select
                value={statusFilter}
                onValueChange={(val) => {
                  setStatusFilter(val);
                  setPage(1);
                }}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Status" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All statuses</SelectItem>
                  <SelectItem value="new">New</SelectItem>
                  <SelectItem value="qualified">Qualified</SelectItem>
                  <SelectItem value="drafted">Drafted</SelectItem>
                  <SelectItem value="sent">Sent</SelectItem>
                  <SelectItem value="duplicate">Duplicate</SelectItem>
                  <SelectItem value="suppressed">Suppressed</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {/* Channel Filter */}
            <div className="w-full md:w-36">
              <Select
                value={channelFilter}
                onValueChange={(val) => {
                  setChannelFilter(val);
                  setPage(1);
                }}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Channel" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All channels</SelectItem>
                  <SelectItem value="email">Email</SelectItem>
                  <SelectItem value="platform">Platform</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {/* Min Score Filter */}
            <div className="w-full md:w-36">
              <Select
                value={minScore}
                onValueChange={(val) => {
                  setMinScore(val);
                  setPage(1);
                }}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Score" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Any score</SelectItem>
                  <SelectItem value="75">75+ Top fit</SelectItem>
                  <SelectItem value="50">50+ Moderate</SelectItem>
                  <SelectItem value="25">25+ Low</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="flex items-center justify-between pt-1 text-xs text-slate-500 dark:text-slate-400">
            <div className="flex items-center gap-4">
              <label className="flex items-center gap-2 cursor-pointer">
                <Checkbox
                  checked={remoteOnly}
                  onCheckedChange={(v) => {
                    setRemoteOnly(v === true);
                    setPage(1);
                  }}
                />
                <span>Remote only</span>
              </label>
            </div>
            <span>
              Total results: <strong className="text-slate-800 dark:text-slate-200">{data?.total ?? 0}</strong>
            </span>
          </div>
        </CardContent>
      </Card>

      {/* Bulk Action Controls */}
      {selectedIds.length > 0 && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-slate-300 bg-slate-900 p-3 text-sm text-slate-100 shadow-md dark:border-slate-700 dark:bg-slate-800">
          <div className="flex items-center gap-2 font-medium">
            <span className="rounded-md bg-slate-800 px-2 py-0.5 text-xs font-bold text-slate-100 dark:bg-slate-700">
              {selectedIds.length}
            </span>
            <span>lead(s) selected</span>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              className="text-slate-900 bg-white hover:bg-slate-100"
              onClick={() => handleBulk("rescore")}
              disabled={busyAction}
            >
              <Sparkles className="h-3.5 w-3.5 text-amber-500" /> Rescore
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="text-slate-900 bg-white hover:bg-slate-100"
              onClick={() => handleBulk("draft")}
              disabled={busyAction}
            >
              <Mail className="h-3.5 w-3.5 text-indigo-500" /> Queue drafts
            </Button>
            <Button
              variant="destructive"
              size="sm"
              onClick={() => handleBulk("never_contact")}
              disabled={busyAction}
            >
              <Ban className="h-3.5 w-3.5" /> Never contact
            </Button>
            <Button
              variant="ghost"
              size="sm"
              className="text-slate-300 hover:text-white"
              onClick={() => setRowSelection({})}
            >
              Clear
            </Button>
          </div>
        </div>
      )}

      {/* Table */}
      <div className="rounded-lg border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900 overflow-hidden shadow-xs">
        <Table>
          <TableHeader>
            {table.getHeaderGroups().map((headerGroup) => (
              <TableRow key={headerGroup.id}>
                {headerGroup.headers.map((header) => (
                  <TableHead key={header.id}>
                    {header.isPlaceholder
                      ? null
                      : flexRender(
                          header.column.columnDef.header,
                          header.getContext()
                        )}
                  </TableHead>
                ))}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody>
            {loading && !data ? (
              <TableRow>
                <TableCell colSpan={columns.length} className="h-32 text-center text-sm text-slate-500">
                  Loading leads…
                </TableCell>
              </TableRow>
            ) : table.getRowModel().rows?.length ? (
              table.getRowModel().rows.map((row) => (
                <TableRow
                  key={row.id}
                  data-state={row.getIsSelected() && "selected"}
                  className="cursor-pointer"
                >
                  {row.getVisibleCells().map((cell) => (
                    <TableCell key={cell.id}>
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </TableCell>
                  ))}
                </TableRow>
              ))
            ) : (
              <TableRow>
                <TableCell colSpan={columns.length} className="h-32 text-center text-sm text-slate-500 dark:text-slate-400">
                  No leads found matching your criteria. Try adjusting your filters or run a collector on the Sources page.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>

        {/* Pagination Bar */}
        <div className="flex items-center justify-between border-t border-slate-200 px-4 py-3 dark:border-slate-800 text-xs text-slate-600 dark:text-slate-400">
          <div>
            Page <span className="font-medium text-slate-900 dark:text-slate-100">{page}</span> of{" "}
            <span className="font-medium text-slate-900 dark:text-slate-100">{totalPages}</span>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={page <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
            >
              Previous
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={page >= totalPages}
              onClick={() => setPage((p) => p + 1)}
            >
              Next
            </Button>
          </div>
        </div>
      </div>

      {/* Lead Detail Slide-over Drawer */}
      <Sheet open={!!selectedLeadId} onOpenChange={(open) => !open && setSelectedLeadId(null)}>
        <SheetContent side="right" className="overflow-y-auto sm:max-w-xl">
          {detailLoading || !leadDetail ? (
            <div className="flex h-full items-center justify-center text-sm text-slate-500">
              Loading lead details…
            </div>
          ) : (
            <div className="space-y-6 pb-8">
              <SheetHeader className="text-left space-y-2">
                <div className="flex items-center gap-2">
                  <Badge variant="outline" className="text-xs uppercase">
                    {leadDetail.source}
                  </Badge>
                  {leadDetail.score !== null && (
                    <Badge
                      variant={
                        leadDetail.score >= 75
                          ? "success"
                          : leadDetail.score >= 50
                          ? "warning"
                          : "secondary"
                      }
                      className="font-mono text-xs font-semibold"
                    >
                      Fit Score: {leadDetail.score}/100
                    </Badge>
                  )}
                  <Badge variant="secondary" className="capitalize text-xs">
                    {leadDetail.status}
                  </Badge>
                </div>
                <SheetTitle className="text-xl leading-snug">
                  {leadDetail.title || "Untitled Opportunity"}
                </SheetTitle>
                <div className="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-400">
                  <span className="font-semibold text-slate-900 dark:text-slate-100">
                    {leadDetail.company}
                  </span>
                  {leadDetail.location && <span>• {leadDetail.location}</span>}
                  {leadDetail.remote && <span>• Remote</span>}
                </div>
              </SheetHeader>

              {/* Drawer Quick Actions */}
              <div className="flex flex-wrap items-center gap-2 border-b border-slate-200 pb-4 dark:border-slate-800">
                {leadDetail.url && (
                  <Button size="sm" variant="outline" asChild>
                    <a href={leadDetail.url} target="_blank" rel="noreferrer">
                      <ExternalLink className="h-3.5 w-3.5" /> View original posting
                    </a>
                  </Button>
                )}
                <Button
                  size="sm"
                  variant="outline"
                  onClick={async () => {
                    await api(`/api/leads/${leadDetail.id}`, {
                      method: "PATCH",
                      body: { status: "qualified" },
                    });
                    setLeadDetail({ ...leadDetail, status: "qualified" });
                    fetchLeads();
                  }}
                >
                  <Check className="h-3.5 w-3.5 text-emerald-600" /> Mark Qualified
                </Button>
                <Button
                  size="sm"
                  variant="destructive"
                  onClick={async () => {
                    await api("/api/leads/bulk", {
                      method: "POST",
                      body: { ids: [leadDetail.id], action: "never_contact" },
                    });
                    setSelectedLeadId(null);
                    fetchLeads();
                  }}
                >
                  <Ban className="h-3.5 w-3.5" /> Never contact
                </Button>
              </div>

              {/* Score & Hook Explanation */}
              {leadDetail.score_reason && (
                <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 dark:border-slate-800 dark:bg-slate-900/60 space-y-2">
                  <div className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                    <Sparkles className="h-3.5 w-3.5 text-amber-500" /> AI Fit Reasoning
                  </div>
                  <p className="text-sm text-slate-700 dark:text-slate-300">
                    {leadDetail.score_reason}
                  </p>
                </div>
              )}

              {leadDetail.hook && (
                <div className="rounded-lg border border-indigo-100 bg-indigo-50/70 p-4 dark:border-indigo-900/40 dark:bg-indigo-950/30 space-y-1.5">
                  <div className="text-xs font-semibold uppercase tracking-wider text-indigo-700 dark:text-indigo-400">
                    Company Hook
                  </div>
                  <p className="text-sm text-indigo-950 dark:text-indigo-200">
                    {leadDetail.hook}
                  </p>
                </div>
              )}

              {/* Public Contact Details */}
              <div className="rounded-lg border border-slate-200 p-4 dark:border-slate-800 space-y-2">
                <div className="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                  Public Contact Info
                </div>
                {leadDetail.contact && Object.keys(leadDetail.contact).length > 0 ? (
                  <div className="space-y-1 text-sm">
                    {leadDetail.contact.email && (
                      <div className="flex items-center gap-2">
                        <Mail className="h-4 w-4 text-slate-400" />
                        <span className="font-mono text-xs">{leadDetail.contact.email}</span>
                      </div>
                    )}
                    {leadDetail.contact.platform && (
                      <div className="flex items-center gap-2">
                        <MessageSquare className="h-4 w-4 text-slate-400" />
                        <span>Platform: {leadDetail.contact.platform}</span>
                      </div>
                    )}
                    {leadDetail.contact.profile_url && (
                      <div className="flex items-center gap-2">
                        <ExternalLink className="h-4 w-4 text-slate-400" />
                        <a
                          href={leadDetail.contact.profile_url}
                          target="_blank"
                          rel="noreferrer"
                          className="text-xs text-indigo-600 hover:underline dark:text-indigo-400"
                        >
                          {leadDetail.contact.profile_url}
                        </a>
                      </div>
                    )}
                  </div>
                ) : (
                  <p className="text-xs text-slate-500 dark:text-slate-400">
                    No direct email publicly listed; routed to platform message queue.
                  </p>
                )}
              </div>

              {/* Tabs for Description & History */}
              <Tabs defaultValue="description">
                <TabsList className="w-full justify-start">
                  <TabsTrigger value="description">Posting Text</TabsTrigger>
                  <TabsTrigger value="history">History &amp; Drafts</TabsTrigger>
                </TabsList>

                <TabsContent value="description" className="space-y-4 pt-2">
                  <div className="rounded-md border border-slate-200 bg-slate-50/50 p-4 font-sans text-sm leading-relaxed text-slate-800 dark:border-slate-800 dark:bg-slate-900/40 dark:text-slate-200 whitespace-pre-wrap max-h-96 overflow-y-auto">
                    {leadDetail.description || leadDetail.raw_text || "No description provided."}
                  </div>
                </TabsContent>

                <TabsContent value="history" className="space-y-4 pt-2">
                  {leadHistory?.drafts && leadHistory.drafts.length > 0 ? (
                    <div className="space-y-3">
                      <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                        Generated Drafts
                      </h4>
                      {leadHistory.drafts.map((d) => (
                        <div
                          key={d.id}
                          className="rounded-lg border border-slate-200 p-3 text-xs dark:border-slate-800 space-y-1.5"
                        >
                          <div className="flex items-center justify-between font-semibold">
                            <span className="capitalize">{d.variant} ({d.channel})</span>
                            <Badge variant="secondary">{d.status}</Badge>
                          </div>
                          {d.subject && (
                            <div className="font-medium text-slate-700 dark:text-slate-300">
                              Subject: {d.subject}
                            </div>
                          )}
                          <p className="text-slate-600 dark:text-slate-400 whitespace-pre-wrap font-sans">
                            {d.body}
                          </p>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-xs text-slate-500 dark:text-slate-400 py-4">
                      No outreach drafts generated yet for this lead.
                    </p>
                  )}
                </TabsContent>
              </Tabs>
            </div>
          )}
        </SheetContent>
      </Sheet>
    </div>
  );
}
