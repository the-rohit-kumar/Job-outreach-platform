"use client";

import * as React from "react";
import { AlertTriangle, Save } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import type { Profile } from "@/lib/types";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { Textarea } from "@/components/ui/textarea";
import { TooltipHint } from "@/components/ui/tooltip";
import { TagEditor } from "@/components/tag-editor";

export default function ProfilePage() {
  const [profile, setProfile] = React.useState<Profile | null>(null);
  const [form, setForm] = React.useState<Profile | null>(null);
  const [message, setMessage] = React.useState<{ kind: "ok" | "err"; text: string } | null>(null);
  const [busy, setBusy] = React.useState(false);

  React.useEffect(() => {
    api<Profile>("/api/profile").then((p) => {
      setProfile(p);
      setForm(p);
    });
  }, []);

  if (!form || !profile) {
    return <div className="text-sm text-slate-500 dark:text-slate-400">Loading profile…</div>;
  }

  const tone = form.tone ?? {};
  const dirty = JSON.stringify(form) !== JSON.stringify(profile);

  function set<K extends keyof Profile>(key: K, value: Profile[K]) {
    setForm((f) => (f ? { ...f, [key]: value } : f));
  }

  function setTone(key: string, value: unknown) {
    setForm((f) => (f ? { ...f, tone: { ...f.tone, [key]: value } } : f));
  }

  async function save() {
    setBusy(true);
    setMessage(null);
    try {
      const updated = await api<Profile>("/api/profile", { method: "PUT", body: form });
      setProfile(updated);
      setForm(updated);
      setMessage({ kind: "ok", text: "Profile saved." });
    } catch (err) {
      setMessage({
        kind: "err",
        text: err instanceof ApiError ? err.message : "Could not save the profile.",
      });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-slate-900 dark:text-slate-100">Profile</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400">
            Drafts are only as honest as this page. Edit the text yourself.
          </p>
        </div>
        <div className="flex items-center gap-3">
          {message && (
            <span
              className={`text-sm ${message.kind === "ok" ? "text-emerald-600 dark:text-emerald-400" : "text-red-600 dark:text-red-400"}`}
            >
              {message.text}
            </span>
          )}
          <Button onClick={save} disabled={!dirty || busy}>
            <Save /> {busy ? "Saving…" : "Save profile"}
          </Button>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>About me</CardTitle>
          <CardDescription>
            Used for scoring leads against you and for drafting messages.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 md:grid-cols-3">
            <div className="space-y-1.5">
              <Label htmlFor="name">Name</Label>
              <Input
                id="name"
                value={form.display_name}
                onChange={(e) => set("display_name", e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                value={form.email}
                onChange={(e) => set("email", e.target.value)}
                placeholder="you@example.com"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="location">Location / timezone</Label>
              <Input
                id="location"
                value={form.location}
                onChange={(e) => set("location", e.target.value)}
                placeholder="Bengaluru, India (IST)"
              />
            </div>
          </div>
          <div className="grid gap-4 md:grid-cols-3">
            <div className="space-y-1.5">
              <Label htmlFor="github_url">GitHub URL</Label>
              <Input
                id="github_url"
                value={form.github_url ?? ""}
                onChange={(e) => set("github_url", e.target.value)}
                placeholder="https://github.com/the-rohit-kumar"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="cv_url">CV Link (Google Drive / PDF)</Label>
              <Input
                id="cv_url"
                value={form.cv_url ?? ""}
                onChange={(e) => set("cv_url", e.target.value)}
                placeholder="https://drive.google.com/..."
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="portfolio_url">Portfolio / Demo Link</Label>
              <Input
                id="portfolio_url"
                value={form.portfolio_url ?? ""}
                onChange={(e) => set("portfolio_url", e.target.value)}
                placeholder="https://..."
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="about">About me block</Label>
            <Textarea
              id="about"
              rows={14}
              value={form.about_me}
              onChange={(e) => set("about_me", e.target.value)}
            />
            <p className="text-xs text-slate-400 dark:text-slate-500">
              Scoring reads this to judge fit; drafting quotes facts from it. Never write
              anything here you would not want repeated to a stranger.
            </p>
          </div>
          <div className="space-y-1.5">
            <Label>Skills</Label>
            <TagEditor
              values={form.skills}
              onChange={(v) => set("skills", v)}
              placeholder="Add a skill and press Enter"
            />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Do-not-mention list</CardTitle>
          <CardDescription>
            The self-check rejects any draft that mentions one of these.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <TagEditor
            values={form.do_not_mention}
            onChange={(v) => set("do_not_mention", v)}
            placeholder="Add a forbidden topic and press Enter"
          />
          <div className="mt-4 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-900/40 dark:bg-amber-950/30 dark:text-amber-200">
            <div className="flex items-center gap-2 font-medium">
              <AlertTriangle className="h-4 w-4" /> Hard drafting rules (enforced by the app)
            </div>
            <ul className="mt-2 list-disc space-y-1 pl-5">
              {(tone.hard_rules ?? []).map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Message tone</CardTitle>
          <CardDescription>Applies to every generated draft.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="grid gap-4 md:grid-cols-4">
            <div className="space-y-1.5">
              <Label>Style</Label>
              <Select value={tone.style ?? "conversational"} onValueChange={(v) => setTone("style", v)}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="conversational">Conversational</SelectItem>
                  <SelectItem value="direct">Direct</SelectItem>
                  <SelectItem value="warm">Warm</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>Formality</Label>
              <Select value={tone.formality ?? "friendly"} onValueChange={(v) => setTone("formality", v)}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="casual">Casual</SelectItem>
                  <SelectItem value="friendly">Friendly</SelectItem>
                  <SelectItem value="formal">Formal</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="maxwords">
                <TooltipHint
                  label="Max email words"
                  hint="Safe default 120. Short cold emails get read; long ones get deleted. Raise only if a draft keeps getting cut off."
                />
              </Label>
              <Input
                id="maxwords"
                type="number"
                min={60}
                max={250}
                value={tone.max_email_words ?? 120}
                onChange={(e) => setTone("max_email_words", Number(e.target.value))}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="maxchars">
                <TooltipHint
                  label="Max LinkedIn note"
                  hint="Safe default 300 characters, the LinkedIn connection-note limit. Going above it means the note gets truncated."
                />
              </Label>
              <Input
                id="maxchars"
                type="number"
                min={100}
                max={400}
                value={tone.max_linkedin_note_chars ?? 300}
                onChange={(e) => setTone("max_linkedin_note_chars", Number(e.target.value))}
              />
            </div>
          </div>

          <Separator />

          <div className="grid gap-3 md:grid-cols-3">
            {(
              [
                ["include_opt_out_line", "Include opt-out line", "A polite one-liner letting them say no. Keeps you out of the angry-reply pile."],
                ["emoji", "Allow emoji", "Off by default: emoji read as marketing to many engineers."],
                ["exclamation_marks", "Allow exclamation marks", "Off by default so drafts stay calm and specific."],
              ] as const
            ).map(([key, label, hint]) => (
              <label
                key={key}
                className="flex cursor-pointer items-start gap-2.5 rounded-md border border-slate-200 p-3 text-sm hover:bg-slate-50 dark:border-slate-800 dark:bg-slate-900/40 dark:hover:bg-slate-800/60 transition-colors"
              >
                <Checkbox
                  checked={Boolean(tone[key])}
                  onCheckedChange={(v) => setTone(key, v === true)}
                />
                <span>
                  <span className="font-medium text-slate-800 dark:text-slate-200">{label}</span>
                  <span className="mt-0.5 block text-xs text-slate-500 dark:text-slate-400">{hint}</span>
                </span>
              </label>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
