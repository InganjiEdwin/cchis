"use client";

import { Bell, Moon, RefreshCcw, Sun } from "lucide-react";
import { useEffect, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import type { ThemePreference } from "@/lib/auth";

type DashboardTopbarProps = {
  title: string;
  subtitle: string;
  lastUpdatedLabel?: string;
  lastUpdatedTone?: "default" | "stale";
  onRefresh?: () => void;
  children?: React.ReactNode;
};

export function DashboardTopbar({
  title,
  subtitle,
  lastUpdatedLabel,
  lastUpdatedTone = "default",
  onRefresh,
  children,
}: DashboardTopbarProps) {
  const { currentUser, updateAppearance } = useAuth();
  const [effectiveTheme, setEffectiveTheme] = useState<"LIGHT" | "DARK">("LIGHT");
  const [isUpdatingTheme, setIsUpdatingTheme] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }

    const mediaQuery = window.matchMedia("(prefers-color-scheme: dark)");
    const resolveEffectiveTheme = () => {
      if (currentUser?.theme_preference === "DARK") {
        setEffectiveTheme("DARK");
        return;
      }
      if (currentUser?.theme_preference === "LIGHT") {
        setEffectiveTheme("LIGHT");
        return;
      }
      setEffectiveTheme(mediaQuery.matches ? "DARK" : "LIGHT");
    };

    resolveEffectiveTheme();
    mediaQuery.addEventListener("change", resolveEffectiveTheme);
    return () => {
      mediaQuery.removeEventListener("change", resolveEffectiveTheme);
    };
  }, [currentUser?.theme_preference]);

  async function handleThemeToggle() {
    if (!currentUser || isUpdatingTheme) {
      return;
    }

    const nextTheme: ThemePreference = effectiveTheme === "DARK" ? "LIGHT" : "DARK";
    setIsUpdatingTheme(true);

    try {
      await updateAppearance(nextTheme);
    } finally {
      setIsUpdatingTheme(false);
    }
  }

  const themeToggleLabel = effectiveTheme === "DARK" ? "Switch to light mode" : "Switch to dark mode";
  const ThemeToggleIcon = effectiveTheme === "DARK" ? Sun : Moon;

  return (
    <header className="dashboard-topbar">
      <div className="dashboard-topbar-copy">
        <h1>{title}</h1>
        <p>{subtitle}</p>
      </div>

      <div className="dashboard-topbar-actions">
        {lastUpdatedLabel ? (
          <div
            className={`dashboard-topbar-status${
              lastUpdatedTone === "stale" ? " dashboard-topbar-status-stale" : ""
            }`}
          >
            <span
              className={`dashboard-topbar-status-dot${
                lastUpdatedTone === "stale" ? " dashboard-topbar-status-dot-stale" : ""
              }`}
              aria-hidden="true"
            />
            <span>Last updated: {lastUpdatedLabel}</span>
          </div>
        ) : null}

        <button
          type="button"
          className="dashboard-icon-button"
          onClick={() => {
            void handleThemeToggle();
          }}
          aria-label={themeToggleLabel}
          title={themeToggleLabel}
          disabled={isUpdatingTheme}
        >
          <ThemeToggleIcon aria-hidden="true" />
        </button>

        <button
          type="button"
          className="dashboard-icon-button"
          onClick={onRefresh}
          aria-label="Refresh dashboard"
        >
          <RefreshCcw aria-hidden="true" />
        </button>

        <button type="button" className="dashboard-icon-button" aria-label="Notifications">
          <Bell aria-hidden="true" />
        </button>

        {children}
      </div>
    </header>
  );
}
