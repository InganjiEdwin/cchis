"use client";

import { Bell, Moon, RefreshCcw, Sun, Waves } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { flushSync } from "react-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { useAuth } from "@/components/auth-provider";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { StatusBadge } from "@/components/ui/status-badge";
import type { ThemePreference } from "@/lib/auth";
import { cn } from "@/lib/cn";
import { fetchTopbarDataViaBff } from "@/lib/dashboard";
import { formatRelativeTimestamp } from "@/lib/freshness";
import { queryKeys } from "@/lib/query-keys";
import { applyThemePreference, persistThemePreference } from "@/lib/theme-preference";

type DashboardTopbarProps = {
  title: string;
  subtitle: string;
  lastUpdatedLabel?: string;
  lastUpdatedTone?: "default" | "stale";
  onRefresh?: () => void;
  showNotifications?: boolean;
  children?: React.ReactNode;
};

type ThemeMode = "LIGHT" | "DARK";

type ViewTransitionLike = {
  ready: Promise<void>;
  finished: Promise<void>;
  updateCallbackDone: Promise<void>;
  skipTransition: () => void;
};

type DocumentWithViewTransition = Document & {
  startViewTransition?: (updateCallback: () => void) => ViewTransitionLike;
};

export function DashboardTopbar({
  title,
  subtitle,
  lastUpdatedLabel,
  lastUpdatedTone = "default",
  onRefresh,
  showNotifications = true,
  children,
}: DashboardTopbarProps) {
  const { currentUser, updateAppearance } = useAuth();
  const router = useRouter();
  const queryClient = useQueryClient();
  const [effectiveTheme, setEffectiveTheme] = useState<ThemeMode>("LIGHT");
  const [isUpdatingTheme, setIsUpdatingTheme] = useState(false);
  const [isRefreshingUi, setIsRefreshingUi] = useState(false);
  const [refreshFeedback, setRefreshFeedback] = useState<string | null>(null);
  const [openPanel, setOpenPanel] = useState<"sync" | "notifications" | null>(null);
  const [activeNotificationFilter, setActiveNotificationFilter] = useState<"all" | "critical" | "warning" | "info">(
    "all",
  );
  const panelRef = useRef<HTMLDivElement | null>(null);
  const topbarQuery = useQuery({
    queryKey: queryKeys.topbar.root(),
    queryFn: fetchTopbarDataViaBff,
    enabled: Boolean(currentUser),
    staleTime: 60_000,
  });

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

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (panelRef.current && !panelRef.current.contains(event.target as Node)) {
        setOpenPanel(null);
      }
    }

    if (!openPanel) {
      return;
    }

    document.addEventListener("mousedown", handleClickOutside);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [openPanel]);

  function commitTheme(themePreference: ThemePreference) {
    flushSync(() => {
      setEffectiveTheme(themePreference as ThemeMode);
    });
    applyThemePreference(themePreference);
    persistThemePreference(themePreference);
  }

  function setThemeTransitionOrigin(buttonElement: HTMLButtonElement) {
    if (typeof document === "undefined") {
      return;
    }

    const rect = buttonElement.getBoundingClientRect();
    const x = rect.left + rect.width / 2;
    const y = rect.top + rect.height / 2;
    document.documentElement.style.setProperty("--theme-transition-origin-x", `${x}px`);
    document.documentElement.style.setProperty("--theme-transition-origin-y", `${y}px`);
  }

  async function handleThemeToggle(buttonElement: HTMLButtonElement) {
    if (!currentUser || isUpdatingTheme) {
      return;
    }

    const nextTheme: ThemePreference = effectiveTheme === "DARK" ? "LIGHT" : "DARK";
    const previousTheme = effectiveTheme;
    setThemeTransitionOrigin(buttonElement);
    setIsUpdatingTheme(true);

    try {
      const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      const documentWithViewTransition = document as DocumentWithViewTransition;

      if (!prefersReducedMotion && documentWithViewTransition.startViewTransition) {
        const transition = documentWithViewTransition.startViewTransition(() => {
          commitTheme(nextTheme);
        });

        await transition.ready.catch(() => undefined);
      } else {
        commitTheme(nextTheme);
      }

      await updateAppearance(nextTheme);
    } catch (error) {
      commitTheme(previousTheme);
      throw error;
    } finally {
      setIsUpdatingTheme(false);
    }
  }

  async function handleDataRefresh() {
    if (isRefreshingUi) {
      return;
    }

    setIsRefreshingUi(true);
    setRefreshFeedback(null);

    try {
      await Promise.resolve(onRefresh?.());
      await queryClient.invalidateQueries({
        predicate: (query) => Array.isArray(query.queryKey) && query.queryKey[0] !== "auth",
      });
      router.refresh();
      setRefreshFeedback("Data refreshed just now");
      setOpenPanel(null);
      window.setTimeout(() => {
        setRefreshFeedback((currentValue) => (currentValue === "Data refreshed just now" ? null : currentValue));
      }, 2200);
    } finally {
      setIsRefreshingUi(false);
    }
  }

  const themeToggleLabel = effectiveTheme === "DARK" ? "Switch to light mode" : "Switch to dark mode";
  const ThemeToggleIcon = effectiveTheme === "DARK" ? Sun : Moon;
  const notifications = topbarQuery.data?.notifications ?? [];
  const unreadCount = notifications.length;
  const feedStatuses = topbarQuery.data?.feeds ?? [];
  const visibleNotifications = useMemo(() => {
    if (activeNotificationFilter === "all") {
      return notifications;
    }

    return notifications.filter((item) => item.level === activeNotificationFilter);
  }, [activeNotificationFilter, notifications]);

  return (
    <header className="sticky top-0 z-30 -mx-[1.4rem] mb-5 flex w-[calc(100%+2.8rem)] min-w-0 max-w-none flex-wrap items-center justify-between gap-4 border-b border-[var(--dashboard-topbar-border)] bg-[var(--dashboard-topbar-surface)] px-[1.4rem] py-4 backdrop-blur max-[960px]:flex-col max-[960px]:items-start max-[640px]:-mx-4 max-[640px]:mb-[1.2rem] max-[640px]:w-[calc(100%+2rem)] max-[640px]:px-4">
      <div className="min-w-0 space-y-0.5">
        <h1 className="m-0 text-[1.375rem] font-semibold leading-[1.15] tracking-[-0.04em] text-[var(--dashboard-topbar-title)] max-[640px]:text-[1.4rem]">
          {title}
        </h1>
        <p className="m-0 text-sm font-medium text-[var(--dashboard-topbar-subtitle)]">{subtitle}</p>
      </div>

      <div
        ref={panelRef}
        className="relative flex flex-wrap items-center justify-end gap-3 max-[960px]:w-full max-[960px]:justify-start"
      >
        {lastUpdatedLabel ? (
          <div
            className={cn(
              "inline-flex items-center gap-2 text-[0.7rem] font-medium text-[#8191a9]",
              lastUpdatedTone === "stale" && "text-[#9b5a2a]",
            )}
          >
            <span
              className={cn(
                "size-[0.45rem] rounded-full bg-[#a9440f]",
                lastUpdatedTone === "stale" && "bg-[#d17a22] shadow-[0_0_0_0.15rem_rgba(209,122,34,0.14)]",
              )}
              aria-hidden="true"
            />
            <span>Last updated: {lastUpdatedLabel}</span>
          </div>
        ) : null}

        {refreshFeedback ? (
          <StatusBadge tone="success" className="px-3 py-1 tracking-[0.14em]">
            {refreshFeedback}
          </StatusBadge>
        ) : null}

        <Button
          variant="secondary"
          size="icon"
          className="size-9 rounded-[0.8rem] border-[var(--dashboard-icon-button-border)] bg-[var(--dashboard-icon-button-surface)] text-[var(--dashboard-icon-button-ink)] transition-[background-color,border-color,color,transform] duration-300 hover:text-[var(--dashboard-icon-button-ink-hover)] active:scale-[0.96]"
          onClick={(event) => {
            void handleThemeToggle(event.currentTarget).catch((error) => {
              console.error("Unable to update theme preference", error);
            });
          }}
          aria-label={themeToggleLabel}
          title={themeToggleLabel}
          disabled={isUpdatingTheme}
        >
          <ThemeToggleIcon className="size-4 transition-transform duration-500" aria-hidden="true" />
        </Button>

        <div className="relative">
          <Button
            variant="secondary"
            size="icon"
            className="size-9 rounded-[0.8rem] border-[var(--dashboard-icon-button-border)] bg-[var(--dashboard-icon-button-surface)] text-[var(--dashboard-icon-button-ink)] hover:text-[var(--dashboard-icon-button-ink-hover)]"
            onClick={() => setOpenPanel((currentValue) => (currentValue === "sync" ? null : "sync"))}
            aria-label="Open sync controls"
          >
            <RefreshCcw className={cn("size-4", isRefreshingUi && "animate-spin")} aria-hidden="true" />
          </Button>

          {openPanel === "sync" ? (
            <Card className="absolute right-0 top-[calc(100%+0.75rem)] z-20 w-[20rem] rounded-[1.4rem] px-4 py-4 shadow-panel">
              <div className="flex items-center gap-3">
                <Waves className="size-4 text-brand" aria-hidden="true" />
                <div>
                  <strong className="block text-sm font-semibold text-panel-strong">System sync</strong>
                  <p className="mt-1 text-xs text-panel-muted">Refresh dashboard data feeds, not the browser tab.</p>
                </div>
              </div>

              <div className="mt-4 space-y-2">
                <button
                  type="button"
                  className="flex w-full items-center justify-between rounded-[1rem] border border-panel-table-wrap bg-[color-mix(in_srgb,var(--dashboard-table-line)_18%,transparent)] px-4 py-3 text-left transition hover:border-[var(--dashboard-icon-button-border)]"
                  onClick={() => {
                    void handleDataRefresh();
                  }}
                >
                  <span>
                    <strong className="block text-sm font-semibold text-panel-strong">Refresh dashboard</strong>
                    <span className="mt-1 block text-xs text-panel-muted">Invalidate dashboard queries and refetch visible data.</span>
                  </span>
                  <RefreshCcw className={cn("size-4 text-brand", isRefreshingUi && "animate-spin")} aria-hidden="true" />
                </button>

                <div className="rounded-[1rem] border border-panel-table-wrap bg-[color-mix(in_srgb,var(--dashboard-table-line)_18%,transparent)] px-4 py-3">
                  <strong className="block text-sm font-semibold text-panel-strong">Feed freshness</strong>
                  <div className="mt-3 space-y-2">
                    {feedStatuses.map((feed) => (
                      <div key={feed.id} className="flex items-center justify-between gap-3 text-xs">
                        <span className="text-panel-copy">{feed.label}</span>
                        <StatusBadge tone={feed.stale ? "warning" : "success"}>
                          {feed.latest_timestamp ? formatRelativeTimestamp(feed.latest_timestamp) : "No data"}
                        </StatusBadge>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </Card>
          ) : null}
        </div>

        {showNotifications ? (
          <div className="relative">
            <Button
              variant="secondary"
              size="icon"
              className="relative size-9 rounded-[0.8rem] border-[var(--dashboard-icon-button-border)] bg-[var(--dashboard-icon-button-surface)] text-[var(--dashboard-icon-button-ink)] hover:text-[var(--dashboard-icon-button-ink-hover)]"
              aria-label="Open notifications"
              onClick={() => setOpenPanel((currentValue) => (currentValue === "notifications" ? null : "notifications"))}
            >
              <Bell className="size-4" aria-hidden="true" />
              {unreadCount > 0 ? (
                <span className="absolute -right-1 -top-1 inline-flex min-w-[1.1rem] items-center justify-center rounded-full bg-[color:var(--danger)] px-1 text-[0.62rem] font-semibold leading-4 text-white">
                  {unreadCount}
                </span>
              ) : null}
            </Button>

            {openPanel === "notifications" ? (
              <Card className="absolute right-0 top-[calc(100%+0.75rem)] z-20 w-[24rem] rounded-[1.5rem] px-5 py-5 shadow-panel">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <h3 className="text-lg font-semibold text-panel-strong">Notifications</h3>
                  <p className="mt-1 text-xs text-panel-muted">Derived from visible alerts, ward risk, and feed freshness</p>
                </div>
                <StatusBadge tone={unreadCount ? "info" : "default"}>{unreadCount} visible</StatusBadge>
              </div>

              <div className="mt-4 flex flex-wrap gap-2">
                {[
                  { value: "all", label: "All" },
                  { value: "critical", label: "Critical" },
                  { value: "warning", label: "Warnings" },
                  { value: "info", label: "Info" },
                ].map((filter) => (
                  <button
                    key={filter.value}
                    type="button"
                    className={cn(
                      "inline-flex h-9 items-center justify-center rounded-pill border px-3 text-sm font-semibold transition",
                      activeNotificationFilter === filter.value
                        ? "border-brand bg-brand text-white"
                        : "border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] text-panel-copy",
                    )}
                    onClick={() => setActiveNotificationFilter(filter.value as "all" | "critical" | "warning" | "info")}
                  >
                    {filter.label}
                  </button>
                ))}
              </div>

              <div className="mt-5 max-h-[26rem] space-y-5 overflow-y-auto pr-1">
                {topbarQuery.isPending ? (
                  <p className="text-sm text-panel-muted">Loading notifications...</p>
                ) : visibleNotifications.length ? (
                  <div className="space-y-3">
                    {visibleNotifications.map((item) => (
                      <Link
                        key={item.id}
                        href={item.href}
                        className={cn(
                          "block rounded-[1.2rem] border px-4 py-4 transition",
                          item.level === "critical" &&
                            "border-[color-mix(in_srgb,var(--danger)_18%,white)] bg-[color-mix(in_srgb,var(--danger)_8%,white)] hover:border-[color:var(--danger)]/35 dark:border-[color-mix(in_srgb,var(--danger)_26%,transparent)] dark:bg-[color-mix(in_srgb,var(--danger)_12%,transparent)]",
                          item.level === "warning" &&
                            "border-[color-mix(in_srgb,var(--warning)_18%,white)] bg-[color-mix(in_srgb,var(--warning)_8%,white)] hover:border-[color:var(--warning)]/35 dark:border-[color-mix(in_srgb,var(--warning)_26%,transparent)] dark:bg-[color-mix(in_srgb,var(--warning)_12%,transparent)]",
                          item.level === "info" &&
                            "border-panel-table-wrap bg-[color-mix(in_srgb,var(--dashboard-table-line)_18%,transparent)] hover:border-[var(--dashboard-icon-button-border)]",
                        )}
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <strong className="block text-sm font-semibold text-panel-strong">{item.title}</strong>
                            <p className="mt-1 text-xs leading-5 text-panel-copy">{item.context}</p>
                          </div>
                          <span
                            className={cn(
                              "text-[0.68rem] font-semibold uppercase tracking-[0.14em]",
                              item.level === "critical" && "text-[color:var(--danger)]",
                              item.level === "warning" && "text-[color:var(--warning)]",
                              item.level === "info" && "text-panel-subtle",
                            )}
                          >
                            {formatRelativeTimestamp(item.timestamp)}
                          </span>
                        </div>
                        <p className="mt-3 text-xs font-semibold uppercase tracking-[0.14em] text-brand">{item.action}</p>
                      </Link>
                    ))}
                  </div>
                ) : (
                  <p className="text-sm text-panel-muted">No notifications are visible for the current dashboard scope.</p>
                )}
              </div>
              </Card>
            ) : null}
          </div>
        ) : null}

        {children}
      </div>
    </header>
  );
}
