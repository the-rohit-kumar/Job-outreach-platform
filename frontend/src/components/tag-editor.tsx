"use client";

import * as React from "react";
import { X } from "lucide-react";
import { Input } from "@/components/ui/input";

export function TagEditor({
  values,
  onChange,
  placeholder,
  id,
}: {
  values: string[];
  onChange: (next: string[]) => void;
  placeholder: string;
  id?: string;
}) {
  const [draft, setDraft] = React.useState("");

  function add() {
    const v = draft.trim();
    if (!v) return;
    if (!values.includes(v)) onChange([...values, v]);
    setDraft("");
  }

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-1.5">
        {values.map((v) => (
          <span
            key={v}
            className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-slate-100 px-2.5 py-1 text-xs text-slate-700 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200"
          >
            {v}
            <button
              type="button"
              aria-label={`Remove ${v}`}
              className="text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 cursor-pointer"
              onClick={() => onChange(values.filter((x) => x !== v))}
            >
              <X className="h-3 w-3" />
            </button>
          </span>
        ))}
        {values.length === 0 && (
          <span className="text-xs text-slate-400 dark:text-slate-500">Nothing added yet.</span>
        )}
      </div>
      <div className="flex gap-2">
        <Input
          id={id}
          value={draft}
          placeholder={placeholder}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              add();
            }
          }}
        />
        <button
          type="button"
          onClick={add}
          className="rounded-md border border-slate-300 px-3 text-sm text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800 cursor-pointer"
        >
          Add
        </button>
      </div>
    </div>
  );
}
