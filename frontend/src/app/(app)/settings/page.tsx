"use client";

import * as React from "react";
import {
  AlertCircle,
  CheckCircle2,
  Clock,
  Flame,
  Mail,
  RefreshCw,
  Save,
  Shield,
  Trash2,
  UserX,
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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

type SettingItem = {
  key: string;
  value: any;
  type: string;
  tooltip: string;
};

type GmailStatus = {
  connected: boolean;
  address: string;
  client_id_configured: boolean;
};

type WarmupStatus = {
  day: number;
  cap: number;
  sent_today: number;
  remaining_today: number;
  started_at: string;
  paused: boolean;
  pause_reason: string;
};

type SuppressionItem = {
  id: number;
  kind: string;
  value: string;
  reason: string;
  source: string;
  created_at: string;
};

export default function SettingsPage() {
  const [settingsList, setSettingsList] = React.useState<SettingItem[]>([]);
  const [rawSettings, setRawSettings] = React.useState<Record<string, any>>({});
  const [warmup, setWarmup] = React.useState<WarmupStatus | null>(null);
  const [gmail, setGmail] = React.useState<GmailStatus | null>(null);
  const [suppressions, setSuppressions] = React.useState<SuppressionItem[]>([]);

  const [formValues, setFormValues] = React.useState<Record<string, any>>({});
  const [newSuppression, setNewSuppression] = React.useState({ kind: "email", value: "", reason: "" });

  const [busy, setBusy] = React.useState(false);
  const [message, setMessage] = React.useState<{ type: "ok" | "err"; text: string } | null>(null);

  const loadData = React.useCallback(async () => {
    try {
      const [settingsData, gmailData, suppData] = await Promise.all([
        api<{ settings: SettingItem[]; raw: Record<string, any>; warmup: WarmupStatus }>("/api/settings"),
        api<GmailStatus>("/api/gmail/status"),
        api<SuppressionItem[]>("/api/settings/suppression"),
      ]);

      setSettingsList(settingsData.settings || []);
      setRawSettings(settingsData.raw || {});
      setFormValues(settingsData.raw || {});
      setWarmup(settingsData.warmup || null);
      setGmail(gmailData);
      setSuppressions(suppData || []);
    } catch (err: any) {
      setMessage({ type: "err", text: err.message || "Failed to load settings" });
    }
  }, []);

  React.useEffect(() => {
    loadData();
  }, [loadData]);

  const handleFieldChange = (key: string, val: any) => {
    setFormValues((prev) => ({ ...prev, [key]: val }));
  };

  const handleSave = async () => {
    setBusy(true);
    setMessage(null);
    try {
      await api("/api/settings", {
        method: "PUT",
        body: JSON.stringify({ values: formValues }),
      });
      setMessage({ type: "ok", text: "Settings saved successfully." });
      await loadData();
    } catch (err: any) {
      setMessage({ type: "err", text: err.message || "Failed to save settings." });
    } finally {
      setBusy(false);
    }
  };

  const handleConnectGmail = async () => {
    try {
      const res = await api<{ auth_url: string }>("/api/gmail/auth-url");
      if (res.auth_url) {
        window.location.href = res.auth_url;
      }
    } catch (err: any) {
      setMessage({ type: "err", text: err.message || "Failed to get Google OAuth URL." });
    }
  };

  const handleDisconnectGmail = async () => {
    if (!confirm("Are you sure you want to disconnect Gmail?")) return;
    try {
      await api("/api/gmail/disconnect", { method: "POST" });
      await loadData();
      setMessage({ type: "ok", text: "Gmail disconnected." });
    } catch (err: any) {
      setMessage({ type: "err", text: err.message || "Failed to disconnect Gmail." });
    }
  };

  const handleCheckReplies = async () => {
    setBusy(true);
    try {
      const res = await api<Record<string, any>>("/api/gmail/check-replies", { method: "POST" });
      setMessage({ type: "ok", text: `Checked replies: ${res.matched || 0} matched.` });
    } catch (err: any) {
      setMessage({ type: "err", text: err.message || "Failed to check replies." });
    } finally {
      setBusy(false);
    }
  };

  const handleAddSuppression = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newSuppression.value.trim()) return;
    try {
      await api("/api/settings/suppression", {
        method: "POST",
        body: JSON.stringify(newSuppression),
      });
      setNewSuppression({ kind: "email", value: "", reason: "" });
      const suppData = await api<SuppressionItem[]>("/api/settings/suppression");
      setSuppressions(suppData);
    } catch (err: any) {
      setMessage({ type: "err", text: err.message || "Failed to add suppression." });
    }
  };

  const handleDeleteSuppression = async (id: number) => {
    try {
      await api(`/api/settings/suppression/${id}`, { method: "DELETE" });
      setSuppressions((prev) => prev.filter((s) => s.id !== id));
    } catch (err: any) {
      setMessage({ type: "err", text: err.message || "Failed to remove suppression." });
    }
  };

  const isDirty = JSON.stringify(formValues) !== JSON.stringify(rawSettings);

  return (
    <div className="space-y-6">
      {/* Top Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between border-b border-slate-200 dark:border-slate-800 pb-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-slate-100">
            Settings & Safety
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            Configure Gmail sending, warm-up pacing, daily limits, and suppression list.
          </p>
        </div>

        <div className="flex items-center gap-3">
          {message && (
            <span
              className={`text-xs font-medium ${
                message.type === "ok" ? "text-emerald-600 dark:text-emerald-400" : "text-red-600 dark:text-red-400"
              }`}
            >
              {message.text}
            </span>
          )}
          <Button onClick={handleSave} disabled={!isDirty || busy} className="gap-2">
            <Save className="h-4 w-4" />
            {busy ? "Saving…" : "Save Changes"}
          </Button>
        </div>
      </div>

      <Tabs defaultValue="sending" className="space-y-6">
        <TabsList className="grid w-full grid-cols-3 max-w-md">
          <TabsTrigger value="sending">Gmail & Sending</TabsTrigger>
          <TabsTrigger value="warmup">Warm-up & Limits</TabsTrigger>
          <TabsTrigger value="suppression">Suppression List</TabsTrigger>
        </TabsList>

        {/* Tab 1: Gmail & Sending Schedule */}
        <TabsContent value="sending" className="space-y-6">
          {/* Gmail OAuth Connection Card */}
          <Card className="shadow-sm">
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2.5">
                  <div className="p-2 rounded-lg bg-blue-50 dark:bg-blue-950 text-blue-600 dark:text-blue-400">
                    <Mail className="h-5 w-5" />
                  </div>
                  <div>
                    <CardTitle className="text-base font-bold">Gmail Connection</CardTitle>
                    <CardDescription className="text-xs">
                      Send approved drafts and detect replies via Google OAuth.
                    </CardDescription>
                  </div>
                </div>
                {gmail?.connected ? (
                  <Badge className="bg-emerald-500 text-white gap-1 text-xs px-2.5 py-0.5">
                    <CheckCircle2 className="h-3 w-3" /> Connected
                  </Badge>
                ) : (
                  <Badge variant="outline" className="text-slate-500 text-xs px-2.5 py-0.5">
                    Not Connected
                  </Badge>
                )}
              </div>
            </CardHeader>

            <CardContent className="space-y-4 text-sm">
              <div className="rounded-lg bg-slate-50 dark:bg-slate-900/60 p-4 border border-slate-200/60 dark:border-slate-800 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
                <div>
                  <span className="text-xs text-slate-500 dark:text-slate-400 block font-medium">Account</span>
                  <span className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                    {gmail?.address || "No Gmail account connected"}
                  </span>
                  <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                    No Google password is ever requested or stored. Uses official OAuth2 tokens.
                  </p>
                </div>

                <div className="flex items-center gap-2">
                  {gmail?.connected ? (
                    <>
                      <Button variant="outline" size="sm" onClick={handleCheckReplies} disabled={busy} className="h-8 gap-1.5 text-xs">
                        <RefreshCw className="h-3.5 w-3.5" /> Check Replies
                      </Button>
                      <Button variant="destructive" size="sm" onClick={handleDisconnectGmail} className="h-8 text-xs">
                        Disconnect
                      </Button>
                    </>
                  ) : (
                    <Button onClick={handleConnectGmail} size="sm" className="h-8 text-xs bg-blue-600 hover:bg-blue-700 text-white">
                      Connect Gmail
                    </Button>
                  )}
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Send Window & Human Spacing Card */}
          <Card className="shadow-sm">
            <CardHeader className="pb-3">
              <div className="flex items-center gap-2.5">
                <div className="p-2 rounded-lg bg-amber-50 dark:bg-amber-950 text-amber-600 dark:text-amber-400">
                  <Clock className="h-5 w-5" />
                </div>
                <div>
                  <CardTitle className="text-base font-bold">Send Window & Human Spacing</CardTitle>
                  <CardDescription className="text-xs">
                    Controls when emails leave your machine and prevents mechanical sending bursts.
                  </CardDescription>
                </div>
              </div>
            </CardHeader>

            <CardContent className="space-y-4">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <Label htmlFor="window_start" className="text-xs font-semibold">
                    Send Window Start
                  </Label>
                  <Input
                    id="window_start"
                    value={formValues["send.window_start"] ?? "09:00"}
                    onChange={(e) => handleFieldChange("send.window_start", e.target.value)}
                    placeholder="09:00"
                  />
                  <span className="text-[11px] text-slate-500">Local time when queue begins dispatching.</span>
                </div>

                <div className="space-y-1.5">
                  <Label htmlFor="window_end" className="text-xs font-semibold">
                    Send Window End
                  </Label>
                  <Input
                    id="window_end"
                    value={formValues["send.window_end"] ?? "18:00"}
                    onChange={(e) => handleFieldChange("send.window_end", e.target.value)}
                    placeholder="18:00"
                  />
                  <span className="text-[11px] text-slate-500">Sending pauses after this time until tomorrow.</span>
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-2 border-t border-slate-100 dark:border-slate-800">
                <div className="space-y-1.5">
                  <Label htmlFor="spacing_min" className="text-xs font-semibold">
                    Min Delay Between Emails (minutes)
                  </Label>
                  <Input
                    id="spacing_min"
                    type="number"
                    value={formValues["send.spacing_minutes_min"] ?? 3}
                    onChange={(e) => handleFieldChange("send.spacing_minutes_min", parseInt(e.target.value) || 1)}
                  />
                  <span className="text-[11px] text-slate-500">Human gap protection (safe default: 3 min).</span>
                </div>

                <div className="space-y-1.5">
                  <Label htmlFor="spacing_max" className="text-xs font-semibold">
                    Max Delay Between Emails (minutes)
                  </Label>
                  <Input
                    id="spacing_max"
                    type="number"
                    value={formValues["send.spacing_minutes_max"] ?? 8}
                    onChange={(e) => handleFieldChange("send.spacing_minutes_max", parseInt(e.target.value) || 5)}
                  />
                  <span className="text-[11px] text-slate-500">Randomized interval upper bound (safe default: 8 min).</span>
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Tab 2: Warm-up & Pipeline Limits */}
        <TabsContent value="warmup" className="space-y-6">
          {/* Active Warm-up Status */}
          {warmup && (
            <Card className="shadow-sm border-emerald-200/60 dark:border-emerald-900/50 bg-gradient-to-r from-emerald-50/40 to-transparent dark:from-emerald-950/20">
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Flame className="h-5 w-5 text-emerald-600 dark:text-emerald-400" />
                    <CardTitle className="text-base font-bold">Email Warm-up Status: Day {warmup.day}</CardTitle>
                  </div>
                  {warmup.paused ? (
                    <Badge variant="destructive">Paused: {warmup.pause_reason}</Badge>
                  ) : (
                    <Badge className="bg-emerald-600 text-white">Active Warm-up</Badge>
                  )}
                </div>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="grid grid-cols-3 gap-4 text-center">
                  <div className="p-3 rounded-lg bg-white dark:bg-slate-900 border border-slate-200/60 dark:border-slate-800">
                    <span className="text-xs text-slate-500 block">Today's Cap</span>
                    <span className="text-xl font-bold text-slate-900 dark:text-slate-100">{warmup.cap}</span>
                  </div>
                  <div className="p-3 rounded-lg bg-white dark:bg-slate-900 border border-slate-200/60 dark:border-slate-800">
                    <span className="text-xs text-slate-500 block">Sent Today</span>
                    <span className="text-xl font-bold text-slate-900 dark:text-slate-100">{warmup.sent_today}</span>
                  </div>
                  <div className="p-3 rounded-lg bg-white dark:bg-slate-900 border border-slate-200/60 dark:border-slate-800">
                    <span className="text-xs text-slate-500 block">Remaining Today</span>
                    <span className="text-xl font-bold text-emerald-600 dark:text-emerald-400">{warmup.remaining_today}</span>
                  </div>
                </div>

                <div className="text-xs text-slate-500 dark:text-slate-400 pt-1">
                  <strong>Warm-up schedule:</strong> Days 1–3: 10/day • Days 4–7: 20/day • Days 8–14: 30/day • Day 15+: 50/day. Auto-pauses if bounce rate exceeds 5%.
                </div>
              </CardContent>
            </Card>
          )}

          {/* Daily Pipeline Targets */}
          <Card className="shadow-sm">
            <CardHeader className="pb-3">
              <CardTitle className="text-base font-bold">Daily Pipeline Targets</CardTitle>
              <CardDescription className="text-xs">
                Target volumes for collection, qualification, and reviews.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                <div className="space-y-1.5">
                  <Label htmlFor="t_collected" className="text-xs font-semibold">Collected Target</Label>
                  <Input
                    id="t_collected"
                    type="number"
                    value={formValues["daily.target_collected"] ?? 300}
                    onChange={(e) => handleFieldChange("daily.target_collected", parseInt(e.target.value) || 100)}
                  />
                  <span className="text-[11px] text-slate-400">Target raw postings to pull.</span>
                </div>

                <div className="space-y-1.5">
                  <Label htmlFor="t_qualified" className="text-xs font-semibold">Qualified Target</Label>
                  <Input
                    id="t_qualified"
                    type="number"
                    value={formValues["daily.target_qualified"] ?? 100}
                    onChange={(e) => handleFieldChange("daily.target_qualified", parseInt(e.target.value) || 50)}
                  />
                  <span className="text-[11px] text-slate-400">Postings clearing score 60+.</span>
                </div>

                <div className="space-y-1.5">
                  <Label htmlFor="t_drafts" className="text-xs font-semibold">Drafts Target</Label>
                  <Input
                    id="t_drafts"
                    type="number"
                    value={formValues["daily.target_drafts"] ?? 50}
                    onChange={(e) => handleFieldChange("daily.target_drafts", parseInt(e.target.value) || 20)}
                  />
                  <span className="text-[11px] text-slate-400">Drafts queued for review.</span>
                </div>

                <div className="space-y-1.5">
                  <Label htmlFor="t_sent" className="text-xs font-semibold">Sent Target</Label>
                  <Input
                    id="t_sent"
                    type="number"
                    value={formValues["daily.target_sent"] ?? 35}
                    onChange={(e) => handleFieldChange("daily.target_sent", parseInt(e.target.value) || 10)}
                  />
                  <span className="text-[11px] text-slate-400">Dispatched outreach goal.</span>
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Tab 3: Suppression List */}
        <TabsContent value="suppression" className="space-y-6">
          <Card className="shadow-sm">
            <CardHeader className="pb-3">
              <div className="flex items-center gap-2.5">
                <div className="p-2 rounded-lg bg-red-50 dark:bg-red-950 text-red-600 dark:text-red-400">
                  <Shield className="h-5 w-5" />
                </div>
                <div>
                  <CardTitle className="text-base font-bold">Suppression & Opt-Outs</CardTitle>
                  <CardDescription className="text-xs">
                    Contacts and domains on this list are permanently blocked across all collectors and drafts.
                  </CardDescription>
                </div>
              </div>
            </CardHeader>

            <CardContent className="space-y-6">
              {/* Add to suppression form */}
              <form onSubmit={handleAddSuppression} className="p-4 rounded-lg bg-slate-50 dark:bg-slate-900 border border-slate-200/60 dark:border-slate-800 space-y-3">
                <Label className="text-xs font-semibold">Add New Suppression Rule</Label>
                <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
                  <div>
                    <select
                      className="w-full h-9 rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-950 px-3 py-1 text-xs"
                      value={newSuppression.kind}
                      onChange={(e) => setNewSuppression((prev) => ({ ...prev, kind: e.target.value }))}
                    >
                      <option value="email">Email</option>
                      <option value="domain">Company Domain</option>
                      <option value="person">Person Name</option>
                    </select>
                  </div>
                  <div className="sm:col-span-2">
                    <Input
                      placeholder="e.g. competitor.com or alex@domain.com"
                      value={newSuppression.value}
                      onChange={(e) => setNewSuppression((prev) => ({ ...prev, value: e.target.value }))}
                      className="h-9 text-xs"
                    />
                  </div>
                  <div>
                    <Button type="submit" size="sm" className="w-full h-9 text-xs">
                      Add to Suppression
                    </Button>
                  </div>
                </div>
              </form>

              {/* Suppression Table */}
              <div className="border border-slate-200 dark:border-slate-800 rounded-lg overflow-hidden">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="text-xs">Type</TableHead>
                      <TableHead className="text-xs">Value</TableHead>
                      <TableHead className="text-xs">Reason</TableHead>
                      <TableHead className="text-xs">Source</TableHead>
                      <TableHead className="text-xs w-16">Action</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {suppressions.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={5} className="text-center py-6 text-xs text-slate-500">
                          Suppression list is currently empty.
                        </TableCell>
                      </TableRow>
                    ) : (
                      suppressions.map((item) => (
                        <TableRow key={item.id}>
                          <TableCell className="text-xs font-semibold uppercase">{item.kind}</TableCell>
                          <TableCell className="text-xs font-mono">{item.value}</TableCell>
                          <TableCell className="text-xs text-slate-500">{item.reason || "Manual opt-out"}</TableCell>
                          <TableCell className="text-xs text-slate-400 capitalize">{item.source}</TableCell>
                          <TableCell>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => handleDeleteSuppression(item.id)}
                              className="h-7 w-7 p-0 text-red-500 hover:text-red-700"
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                            </Button>
                          </TableCell>
                        </TableRow>
                      ))
                    )}
                  </TableBody>
                </Table>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
