"use client";

import * as React from "react";
import { Moon, Sun, Monitor } from "lucide-react";
import { useTheme } from "@/components/theme-provider";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

interface ThemeToggleProps {
  variant?: "icon" | "segmented";
  className?: string;
}

export function ThemeToggle({ variant = "icon", className = "" }: ThemeToggleProps) {
  const { theme, resolvedTheme, setTheme, toggleTheme } = useTheme();
  const [mounted, setMounted] = React.useState(false);

  React.useEffect(() => {
    setMounted(true);
  }, []);

  if (variant === "segmented") {
    return (
      <div
        className={`inline-flex items-center rounded-lg border border-slate-200 bg-slate-100 p-0.5 text-xs text-slate-600 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-400 ${className}`}
        role="group"
        aria-label="Theme preference"
      >
        <button
          type="button"
          onClick={() => setTheme("light")}
          className={`inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 font-medium transition-all ${
            mounted && theme === "light"
              ? "bg-white text-slate-900 shadow-xs dark:bg-slate-800 dark:text-slate-100"
              : "hover:text-slate-900 dark:hover:text-slate-200"
          }`}
          aria-pressed={mounted && theme === "light"}
        >
          <Sun className="h-3.5 w-3.5 text-amber-500" />
          <span>Light</span>
        </button>
        <button
          type="button"
          onClick={() => setTheme("dark")}
          className={`inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 font-medium transition-all ${
            mounted && theme === "dark"
              ? "bg-white text-slate-900 shadow-xs dark:bg-slate-800 dark:text-slate-100"
              : "hover:text-slate-900 dark:hover:text-slate-200"
          }`}
          aria-pressed={mounted && theme === "dark"}
        >
          <Moon className="h-3.5 w-3.5 text-indigo-400" />
          <span>Dark</span>
        </button>
        <button
          type="button"
          onClick={() => setTheme("system")}
          className={`inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 font-medium transition-all ${
            mounted && theme === "system"
              ? "bg-white text-slate-900 shadow-xs dark:bg-slate-800 dark:text-slate-100"
              : "hover:text-slate-900 dark:hover:text-slate-200"
          }`}
          aria-pressed={mounted && theme === "system"}
        >
          <Monitor className="h-3.5 w-3.5 text-slate-500" />
          <span>System</span>
        </button>
      </div>
    );
  }

  const isDark = resolvedTheme === "dark";
  const label = isDark ? "Switch to light mode" : "Switch to dark mode";

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          onClick={toggleTheme}
          aria-label={label}
          className={`relative inline-flex h-9 w-9 items-center justify-center rounded-md border border-slate-200 bg-white text-slate-700 shadow-xs transition-all hover:bg-slate-100 hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-slate-100 dark:focus-visible:ring-slate-600 cursor-pointer ${className}`}
        >
          {mounted ? (
            isDark ? (
              <Sun className="h-4 w-4 text-amber-400 transition-transform duration-300 hover:rotate-45" />
            ) : (
              <Moon className="h-4 w-4 text-indigo-600 transition-transform duration-300 hover:-rotate-12" />
            )
          ) : (
            <>
              <Sun className="hidden h-4 w-4 text-amber-400 dark:block" />
              <Moon className="block h-4 w-4 text-indigo-600 dark:hidden" />
            </>
          )}
          <span className="sr-only">{label}</span>
        </button>
      </TooltipTrigger>
      <TooltipContent side="bottom" sideOffset={6}>
        {label}
      </TooltipContent>
    </Tooltip>
  );
}
