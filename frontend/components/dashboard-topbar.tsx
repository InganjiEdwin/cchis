"use client";

import { AlertTriangle, Bell, ChevronDown, ChevronUp, Ellipsis, Moon, RefreshCcw, ShieldCheck, Sun, Waves } from "lucide-react";
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
import {
  acknowledgeNotificationViaBff,
  type DashboardNotification,
  type DashboardNotificationStreamEvent,
  type TopbarData,
  dismissNotificationViaBff,
  fetchNotificationStreamTokenViaBff,
  fetchTopbarDataViaBff,
  markAllNotificationsSeenViaBff,
  markNotificationSeenViaBff,
} from "@/lib/dashboard";
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

type NotificationDrawerItem =
  | {
      kind: "single";
      id: string;
      notification: DashboardNotification;
    }
  | {
      kind: "group";
      id: string;
      severity: DashboardNotification["severity"];
      title: string;
      body: string;
      href: string;
      createdAt: string;
      items: DashboardNotification[];
    };

const GROUPING_WINDOW_MINUTES = 30;

function buildNotificationWebsocketUrl(websocketPath: string) {
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ?? "http://localhost:8000/api/v1";
  const backendOrigin = apiBaseUrl.replace(/\/api\/v\d+$/, "");
  const websocketOrigin = backendOrigin.replace(/^http/, "ws");
  return `${websocketOrigin}${websocketPath}`;
}

function reconcileNotificationList(
  notifications: DashboardNotification[],
  incoming: DashboardNotification,
  eventName: DashboardNotificationStreamEvent["event"],
) {
  const withoutIncoming = notifications.filter((item) => item.public_id !== incoming.public_id);

  if (eventName === "notification.created") {
    return [incoming, ...withoutIncoming];
  }

  const existing = notifications.find((item) => item.public_id === incoming.public_id);
  if (!existing) {
    return [incoming, ...withoutIncoming];
  }

  return [incoming, ...withoutIncoming];
}

function reconcileTopbarDataWithStreamEvent(current: TopbarData | undefined, payload: DashboardNotificationStreamEvent) {
  if (!current) {
    return current;
  }

  const nextFeeds = payload.feeds ?? current.feeds;
  const nextFreshness = payload.freshness ?? current.freshness;

  if (!payload.notification || payload.event === "notification.connected" || payload.event === "topbar.snapshot") {
    return {
      ...current,
      unread_count: payload.unread_count,
      highest_unread_severity: payload.highest_unread_severity ?? current.highest_unread_severity,
      system_status: payload.system_status ?? current.system_status,
      feeds: nextFeeds,
      freshness: nextFreshness,
    };
  }

  return {
    ...current,
    unread_count: payload.unread_count,
    highest_unread_severity: payload.highest_unread_severity ?? current.highest_unread_severity,
    system_status: payload.system_status ?? current.system_status,
    feeds: nextFeeds,
    freshness: nextFreshness,
    notifications: reconcileNotificationList(current.notifications, payload.notification, payload.event),
  };
}

function getFreshnessBadgeTone(state: TopbarData["freshness"]["freshness_state"]) {
  if (state === "stale") {
    return "warning";
  }
  if (state === "delayed") {
    return "info";
  }
  return "success";
}

function getNotificationPrimaryActionLabel(item: DashboardNotification) {
  if (item.type === "FEED_STALE") {
    return "Review system state";
  }
  if (item.type === "OPERATIONAL_KPI_THRESHOLD") {
    return "Review KPI";
  }

  return item.href ? "Review" : null;
}

function getNotificationStatusAccent(tone: "success" | "warning" | "danger") {
  if (tone === "danger") {
    return {
      icon: AlertTriangle,
      chipClassName:
        "border-[color-mix(in_srgb,var(--danger)_30%,transparent)] bg-[color-mix(in_srgb,var(--danger)_12%,transparent)] text-[color:var(--danger)]",
      dotClassName: "bg-[color:var(--danger)]",
    };
  }

  if (tone === "warning") {
    return {
      icon: AlertTriangle,
      chipClassName:
        "border-[color-mix(in_srgb,var(--warning)_28%,transparent)] bg-[color-mix(in_srgb,var(--warning)_12%,transparent)] text-[color:var(--warning)]",
      dotClassName: "bg-[color:var(--warning)]",
    };
  }

  return {
    icon: ShieldCheck,
    chipClassName:
      "border-[color-mix(in_srgb,#7fcf96_28%,transparent)] bg-[color-mix(in_srgb,#7fcf96_12%,transparent)] text-[#7fcf96]",
    dotClassName: "bg-[#7fcf96]",
  };
}

function getNotificationBellTone(
  unreadSeverity: TopbarData["highest_unread_severity"] | undefined,
  systemStatus: TopbarData["system_status"] | undefined,
) {
  if (unreadSeverity === "CRITICAL" || systemStatus === "ACTION_REQUIRED") {
    return {
      buttonClassName:
        "border-[color-mix(in_srgb,var(--danger)_26%,transparent)] bg-[color-mix(in_srgb,var(--danger)_10%,transparent)] text-[color:var(--danger)] hover:bg-[color-mix(in_srgb,var(--danger)_16%,transparent)] hover:text-[color:var(--danger)]",
      badgeClassName: "bg-[color:var(--danger)] text-white",
    };
  }

  if (unreadSeverity === "WARNING" || systemStatus === "DATA_FRESHNESS_DEGRADED") {
    return {
      buttonClassName:
        "border-[color-mix(in_srgb,var(--warning)_26%,transparent)] bg-[color-mix(in_srgb,var(--warning)_10%,transparent)] text-[color:var(--warning)] hover:bg-[color-mix(in_srgb,var(--warning)_16%,transparent)] hover:text-[color:var(--warning)]",
      badgeClassName: "bg-[color:var(--warning)] text-[color:var(--surface-950)]",
    };
  }

  if (unreadSeverity === "INFO") {
    return {
      buttonClassName:
        "border-[color-mix(in_srgb,var(--brand)_24%,transparent)] bg-[color-mix(in_srgb,var(--brand)_10%,transparent)] text-brand hover:bg-[color-mix(in_srgb,var(--brand)_16%,transparent)] hover:text-brand",
      badgeClassName: "bg-brand text-white",
    };
  }

  return {
    buttonClassName:
      "border-[var(--dashboard-icon-button-border)] bg-[var(--dashboard-icon-button-surface)] text-[var(--dashboard-icon-button-ink)] hover:text-[var(--dashboard-icon-button-ink-hover)]",
    badgeClassName: "bg-[color:var(--danger)] text-white",
  };
}

function getNotificationSystemStatus(
  topbarData: TopbarData | undefined,
): {
  label: string;
  tone: "success" | "warning" | "danger";
  compactSummary: string;
} {
  const systemStatus = topbarData?.system_status;
  const feeds = topbarData?.feeds ?? [];
  const notifications = topbarData?.notifications ?? [];
  const staleFeedCount = feeds.filter((feed) => feed.stale).length;
  const openDeliveryIssues = notifications.filter(
    (notification) =>
      notification.category === "alert_delivery" &&
      notification.state !== "RESOLVED" &&
      notification.state !== "DISMISSED" &&
      notification.state !== "EXPIRED",
  ).length;
  const criticalUnreadCount = notifications.filter(
    (notification) => notification.state === "NEW" && notification.severity === "CRITICAL",
  ).length;
  const warningUnreadCount = notifications.filter(
    (notification) => notification.state === "NEW" && notification.severity === "WARNING",
  ).length;

  if (criticalUnreadCount > 0 || systemStatus === "ACTION_REQUIRED") {
    return {
      label: "System status: Action required",
      tone: "danger",
      compactSummary: `${criticalUnreadCount || 1} critical ${criticalUnreadCount === 1 ? "alert" : "alerts"} unread`,
    };
  }

  if (staleFeedCount > 0 || openDeliveryIssues > 0 || systemStatus === "DATA_FRESHNESS_DEGRADED") {
    const compactParts = [];
    if (staleFeedCount > 0) {
      compactParts.push(`${staleFeedCount} ${staleFeedCount === 1 ? "feed" : "feeds"} stale`);
    }
    if (openDeliveryIssues > 0) {
      compactParts.push(`${openDeliveryIssues} delivery ${openDeliveryIssues === 1 ? "failure" : "failures"}`);
    }
    if (warningUnreadCount > 0) {
      compactParts.push(`${warningUnreadCount} warning${warningUnreadCount === 1 ? "" : "s"} unread`);
    }
    return {
      label: "System status: Data freshness degraded",
      tone: "warning",
      compactSummary: compactParts.join(" • "),
    };
  }

  if (warningUnreadCount > 0) {
    return {
      label: "System status: Stable with warnings",
      tone: "warning",
      compactSummary: `${warningUnreadCount} warning${warningUnreadCount === 1 ? "" : "s"} unread`,
    };
  }

  return {
    label: "System status: Stable",
    tone: "success",
    compactSummary: "No warnings or delivery issues",
  };
}

function getNotificationSystemContext(topbarData: TopbarData | undefined) {
  const feeds = topbarData?.feeds ?? [];
  const notifications = topbarData?.notifications ?? [];
  const staleFeedCount = feeds.filter((feed) => feed.stale).length;
  const openDeliveryIssues = notifications.filter(
    (notification) =>
      notification.category === "alert_delivery" &&
      notification.state !== "RESOLVED" &&
      notification.state !== "DISMISSED" &&
      notification.state !== "EXPIRED",
  ).length;
  const criticalUnreadCount = notifications.filter(
    (notification) => notification.state === "NEW" && notification.severity === "CRITICAL",
  ).length;
  const warningUnreadCount = notifications.filter(
    (notification) => notification.state === "NEW" && notification.severity === "WARNING",
  ).length;

  const freshnessSummary =
    staleFeedCount > 0
      ? `${staleFeedCount} data ${staleFeedCount === 1 ? "feed" : "feeds"} stale`
      : "All core data feeds fresh";
  const deliverySummary =
    openDeliveryIssues > 0
      ? `${openDeliveryIssues} delivery ${openDeliveryIssues === 1 ? "issue" : "issues"} open`
      : "No delivery failures";

  let attentionSummary = "Monitoring only";
  if (criticalUnreadCount > 0) {
    attentionSummary = `${criticalUnreadCount} critical ${criticalUnreadCount === 1 ? "alert" : "alerts"} unread`;
  } else if (warningUnreadCount > 0) {
    attentionSummary = `${warningUnreadCount} warning ${warningUnreadCount === 1 ? "signal" : "signals"} unread`;
  }

  return {
    summaryLine: `${freshnessSummary} • ${warningUnreadCount} warning${warningUnreadCount === 1 ? "" : "s"} unread`,
    basisLine: "Based on latest feeds and open notifications",
    staleFeedCount,
    openDeliveryIssues,
    warningUnreadCount,
  };
}

function getNotificationCardBody(notification: DashboardNotification) {
  if (notification.type === "FEED_STALE") {
    return "Data is stale and may not reflect current conditions.";
  }

  return notification.body;
}

function groupNotificationsForDrawer(notifications: DashboardNotification[]): NotificationDrawerItem[] {
  const isDataFreshnessItem = (item: DashboardNotification) =>
    (item.category === "system_health" && item.group_key === "data_freshness") ||
    (item.type === "FEED_STALE" && item.source_object_type === "feed");

  const feedStaleItems = notifications.filter(isDataFreshnessItem);
  const nonGroupedItems = notifications.filter((item) => !isDataFreshnessItem(item));

  const drawerItems: NotificationDrawerItem[] = nonGroupedItems.map((notification) => ({
    kind: "single",
    id: notification.public_id,
    notification,
  }));

  if (feedStaleItems.length) {
    const sortedFeedStaleItems = [...feedStaleItems].sort(
      (left, right) => new Date(right.created_at).getTime() - new Date(left.created_at).getTime(),
    );
    const groupedBuckets: DashboardNotification[][] = [];

    for (const notification of sortedFeedStaleItems) {
      const lastBucket = groupedBuckets[groupedBuckets.length - 1];
      if (!lastBucket) {
        groupedBuckets.push([notification]);
        continue;
      }

      const bucketHead = lastBucket[0];
      const minutesFromHead =
        Math.abs(new Date(bucketHead.created_at).getTime() - new Date(notification.created_at).getTime()) / 60000;

      if (minutesFromHead <= GROUPING_WINDOW_MINUTES) {
        lastBucket.push(notification);
      } else {
        groupedBuckets.push([notification]);
      }
    }

    for (const bucket of groupedBuckets) {
      if (bucket.length > 1) {
        const feedLabels = bucket.map((item) => {
          const metadataLabel = typeof item.metadata.feed_label === "string" ? item.metadata.feed_label : null;
          const baseLabel = metadataLabel || item.title;
          return baseLabel.replace(/\s*outdated$/i, "").replace(/\s*:\s*stale$/i, "");
        });

        drawerItems.push({
          kind: "group",
          id: `group-feed-stale-${bucket[0]?.public_id ?? "latest"}`,
          severity: "WARNING",
          title: "Data freshness issue detected",
          body: `${feedLabels.length} feeds are stale: ${feedLabels.join(", ")}.`,
          href: bucket[0]?.href ?? "/system",
          createdAt: bucket[0]?.created_at ?? new Date().toISOString(),
          items: bucket,
        });
        continue;
      }

      drawerItems.push({
        kind: "single",
        id: bucket[0].public_id,
        notification: bucket[0],
      });
    }
  }

  return drawerItems.sort((left, right) => {
    const leftCreatedAt = left.kind === "group" ? left.createdAt : left.notification.created_at;
    const rightCreatedAt = right.kind === "group" ? right.createdAt : right.notification.created_at;
    return new Date(rightCreatedAt).getTime() - new Date(leftCreatedAt).getTime();
  });
}

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
  const [isNotificationStreamConnected, setIsNotificationStreamConnected] = useState(false);
  const [effectiveTheme, setEffectiveTheme] = useState<ThemeMode>("LIGHT");
  const [isUpdatingTheme, setIsUpdatingTheme] = useState(false);
  const [isRefreshingUi, setIsRefreshingUi] = useState(false);
  const [refreshFeedback, setRefreshFeedback] = useState<string | null>(null);
  const [openPanel, setOpenPanel] = useState<"sync" | "notifications" | null>(null);
  const [activeNotificationFilter, setActiveNotificationFilter] = useState<"all" | "critical" | "warning" | "info">(
    "all",
  );
  const [unreadOnly, setUnreadOnly] = useState(false);
  const [isSystemStatusExpanded, setIsSystemStatusExpanded] = useState(false);
  const [expandedNotificationGroups, setExpandedNotificationGroups] = useState<Record<string, boolean>>({});
  const [openOverflowMenuId, setOpenOverflowMenuId] = useState<string | null>(null);
  const panelRef = useRef<HTMLDivElement | null>(null);
  const topbarQuery = useQuery({
    queryKey: queryKeys.topbar.root(),
    queryFn: fetchTopbarDataViaBff,
    enabled: Boolean(currentUser),
    staleTime: 30_000,
    refetchInterval: currentUser && !isNotificationStreamConnected ? 30_000 : false,
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

  useEffect(() => {
    if (!currentUser || !showNotifications || typeof window === "undefined") {
      return;
    }

    let cancelled = false;
    let reconnectTimer: number | null = null;
    let socket: WebSocket | null = null;

    const scheduleReconnect = (delayMs: number) => {
      if (cancelled) {
        return;
      }
      reconnectTimer = window.setTimeout(() => {
        void connect();
      }, delayMs);
    };

    const connect = async () => {
      try {
        const streamToken = await fetchNotificationStreamTokenViaBff();
        if (cancelled) {
          return;
        }

        socket = new WebSocket(
          `${buildNotificationWebsocketUrl(streamToken.websocket_path)}?token=${encodeURIComponent(streamToken.token)}`,
        );

        socket.onmessage = (event) => {
          try {
            const payload = JSON.parse(event.data) as DashboardNotificationStreamEvent;
            if (payload.event?.startsWith("notification.")) {
              if (payload.event === "notification.connected") {
                setIsNotificationStreamConnected(true);
              }
              queryClient.setQueryData<TopbarData | undefined>(queryKeys.topbar.root(), (current) =>
                reconcileTopbarDataWithStreamEvent(current, payload),
              );
            } else if (payload.event === "topbar.snapshot") {
              setIsNotificationStreamConnected(true);
              queryClient.setQueryData<TopbarData | undefined>(queryKeys.topbar.root(), (current) =>
                reconcileTopbarDataWithStreamEvent(current, payload),
              );
            }
          } catch (error) {
            console.error("Unable to parse notification websocket payload", error);
          }
        };

        socket.onerror = () => {
          socket?.close();
        };

        socket.onclose = () => {
          socket = null;
          setIsNotificationStreamConnected(false);
          scheduleReconnect(5000);
        };
      } catch (error) {
        console.error("Unable to establish notification websocket stream", error);
        setIsNotificationStreamConnected(false);
        scheduleReconnect(10000);
      }
    };

    void connect();

    return () => {
      cancelled = true;
      setIsNotificationStreamConnected(false);
      if (reconnectTimer) {
        window.clearTimeout(reconnectTimer);
      }
      socket?.close();
    };
  }, [currentUser, queryClient, showNotifications]);

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
  const unreadCount = topbarQuery.data?.unread_count ?? 0;
  const backendSystemStatus = topbarQuery.data?.system_status;
  const feedStatuses = topbarQuery.data?.feeds ?? [];
  const freshness = topbarQuery.data?.freshness ?? null;
  const notificationSystemStatus = useMemo(() => getNotificationSystemStatus(topbarQuery.data), [topbarQuery.data]);
  const notificationStatusAccent = useMemo(
    () => getNotificationStatusAccent(notificationSystemStatus.tone),
    [notificationSystemStatus.tone],
  );
  const notificationBellTone = useMemo(
    () => getNotificationBellTone(topbarQuery.data?.highest_unread_severity, backendSystemStatus),
    [backendSystemStatus, topbarQuery.data?.highest_unread_severity],
  );
  const notificationSystemContext = useMemo(() => getNotificationSystemContext(topbarQuery.data), [topbarQuery.data]);
  const visibleNotifications = useMemo(() => {
    const scopedNotifications = unreadOnly ? notifications.filter((item) => item.state === "NEW") : notifications;

    if (activeNotificationFilter === "all") {
      return scopedNotifications;
    }

    return scopedNotifications.filter((item) => {
      const level = item.severity === "CRITICAL" ? "critical" : item.severity === "WARNING" ? "warning" : "info";
      return level === activeNotificationFilter;
    });
  }, [activeNotificationFilter, notifications, unreadOnly]);
  const drawerNotifications = useMemo(() => groupNotificationsForDrawer(visibleNotifications), [visibleNotifications]);

  async function refreshNotificationTruth() {
    await queryClient.invalidateQueries({ queryKey: queryKeys.topbar.root() });
  }

  async function handleNotificationSeen(publicId: string) {
    await markNotificationSeenViaBff(publicId);
    await refreshNotificationTruth();
  }

  async function handleNotificationAcknowledge(publicId: string) {
    await acknowledgeNotificationViaBff(publicId);
    await refreshNotificationTruth();
  }

  async function handleNotificationDismiss(publicId: string) {
    await dismissNotificationViaBff(publicId);
    await refreshNotificationTruth();
  }

  async function handleNotificationsSeen(publicIds: string[]) {
    await Promise.all(publicIds.map((publicId) => markNotificationSeenViaBff(publicId)));
    await refreshNotificationTruth();
  }

  async function handleNotificationsDismiss(publicIds: string[]) {
    await Promise.all(publicIds.map((publicId) => dismissNotificationViaBff(publicId)));
    await refreshNotificationTruth();
  }

  async function handleMarkAllSeen() {
    await markAllNotificationsSeenViaBff();
    await refreshNotificationTruth();
  }

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
            aria-label="Open sync summary"
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
                  <div className="flex items-center justify-between gap-3">
                    <strong className="block text-sm font-semibold text-panel-strong">Operational trust</strong>
                    {freshness ? (
                      <StatusBadge tone={getFreshnessBadgeTone(freshness.freshness_state)}>
                        {freshness.freshness_state === "fresh"
                          ? "Fresh"
                          : freshness.freshness_state === "delayed"
                            ? "Delayed"
                            : "Stale"}
                      </StatusBadge>
                    ) : null}
                  </div>
                  <div className="mt-3 space-y-2">
                    <div className="flex items-center justify-between gap-3 text-xs">
                      <span className="text-panel-copy">Model updated</span>
                      <StatusBadge tone={freshness ? getFreshnessBadgeTone(freshness.freshness_state) : "default"}>
                        {freshness?.last_model_run_at ? formatRelativeTimestamp(freshness.last_model_run_at) : "No run"}
                      </StatusBadge>
                    </div>
                    <div className="flex items-center justify-between gap-3 text-xs">
                      <span className="text-panel-copy">Data sync</span>
                      <StatusBadge tone={freshness ? getFreshnessBadgeTone(freshness.freshness_state) : "default"}>
                        {freshness?.last_data_sync_at ? formatRelativeTimestamp(freshness.last_data_sync_at) : "No sync"}
                      </StatusBadge>
                    </div>
                    <div className="flex items-center justify-between gap-3 text-xs">
                      <span className="text-panel-copy">Alerts refreshed</span>
                      <StatusBadge tone={freshness ? getFreshnessBadgeTone(freshness.freshness_state) : "default"}>
                        {freshness?.last_alert_ingestion_at
                          ? formatRelativeTimestamp(freshness.last_alert_ingestion_at)
                          : "No alerts"}
                      </StatusBadge>
                    </div>
                    <div className="flex items-center justify-between gap-3 text-xs">
                      <span className="text-panel-copy">Prediction generated</span>
                      <StatusBadge tone={freshness ? getFreshnessBadgeTone(freshness.freshness_state) : "default"}>
                        {freshness?.prediction_generated_at
                          ? formatRelativeTimestamp(freshness.prediction_generated_at)
                          : "No prediction"}
                      </StatusBadge>
                    </div>
                    <div className="flex items-center justify-between gap-3 text-xs">
                      <span className="text-panel-copy">Notifications live</span>
                      <StatusBadge tone={isNotificationStreamConnected ? "success" : "warning"}>
                        {isNotificationStreamConnected ? "Connected" : "Polling fallback"}
                      </StatusBadge>
                    </div>
                  </div>
                </div>

                <div className="rounded-[1rem] border border-panel-table-wrap bg-[color-mix(in_srgb,var(--dashboard-table-line)_18%,transparent)] px-4 py-3">
                  <strong className="block text-sm font-semibold text-panel-strong">Feed surfaces</strong>
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
              className={cn("relative size-9 rounded-[0.8rem]", notificationBellTone.buttonClassName)}
              aria-label="Open notifications"
              onClick={() => setOpenPanel((currentValue) => (currentValue === "notifications" ? null : "notifications"))}
            >
              <Bell className="size-4" aria-hidden="true" />
              {unreadCount > 0 ? (
                <span
                  className={cn(
                    "absolute -right-1 -top-1 inline-flex min-w-[1.1rem] items-center justify-center rounded-full px-1 text-[0.62rem] font-semibold leading-4",
                    notificationBellTone.badgeClassName,
                  )}
                >
                  {unreadCount}
                </span>
              ) : null}
            </Button>

            {openPanel === "notifications" ? (
              <Card className="absolute right-0 top-[calc(100%+0.75rem)] z-20 w-[34rem] max-w-[calc(100vw-2rem)] rounded-[1.5rem] px-5 py-5 shadow-panel">
              <div>
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0 flex-1">
                    <h3 className="text-lg font-semibold text-panel-strong">Notifications</h3>
                  </div>
                  <div className="flex shrink-0 items-center gap-3 whitespace-nowrap">
                    <StatusBadge tone={unreadCount ? "info" : "default"} className="whitespace-nowrap px-3 py-1.5">
                      {unreadCount} unread
                    </StatusBadge>
                    <button
                      type="button"
                      className="whitespace-nowrap text-xs font-semibold uppercase tracking-[0.14em] text-brand"
                      onClick={() => {
                        void handleMarkAllSeen();
                      }}
                    >
                      Mark all seen
                    </button>
                  </div>
                </div>

                <div className="mt-3 rounded-[1rem] border border-panel-table-wrap/80 bg-[color-mix(in_srgb,var(--dashboard-table-line)_12%,transparent)] px-3.5 py-3">
                  <div className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-2">
                    <button
                      type="button"
                      className="min-w-0 text-left"
                      onClick={() => {
                        setOpenPanel(null);
                        router.push("/system");
                      }}
                    >
                      <div className="flex items-center gap-2 text-sm leading-6">
                        <span className="text-panel-subtle">System status:</span>
                        <span
                          className={cn("inline-block size-2 rounded-full", notificationStatusAccent.dotClassName)}
                          aria-hidden="true"
                        />
                        <span className="font-medium text-panel-strong">
                          {notificationSystemStatus.label.replace("System status: ", "")}
                        </span>
                      </div>
                      <p className="mt-1 text-sm leading-6 text-panel-muted">{notificationSystemStatus.compactSummary}</p>
                    </button>
                    <button
                      type="button"
                      className="inline-flex items-center justify-end gap-1.5 self-center whitespace-nowrap text-[0.72rem] font-semibold uppercase tracking-[0.14em] text-brand"
                      onClick={() => setIsSystemStatusExpanded((currentValue) => !currentValue)}
                    >
                      {isSystemStatusExpanded ? "Hide details" : "View details"}
                      {isSystemStatusExpanded ? <ChevronUp className="size-3.5" aria-hidden="true" /> : <ChevronDown className="size-3.5" aria-hidden="true" />}
                    </button>
                  </div>
                  {isSystemStatusExpanded ? (
                    <div className="mt-3 grid gap-2 border-t border-panel-table-wrap/70 pt-3 text-xs text-panel-copy">
                      <div className="flex items-center justify-between gap-3">
                        <span>Data feeds stale</span>
                        <span className="font-semibold text-panel-strong">{notificationSystemContext.staleFeedCount}</span>
                      </div>
                      <div className="flex items-center justify-between gap-3">
                        <span>Delivery failures</span>
                        <span className="font-semibold text-panel-strong">{notificationSystemContext.openDeliveryIssues}</span>
                      </div>
                      <div className="flex items-center justify-between gap-3">
                        <span>Warning signals unread</span>
                        <span className="font-semibold text-panel-strong">{notificationSystemContext.warningUnreadCount}</span>
                      </div>
                      <p className="pt-1 text-[0.72rem] leading-5 text-panel-subtle">
                        {notificationSystemContext.basisLine}
                      </p>
                    </div>
                  ) : null}
                </div>

                <p className="mt-3 text-xs leading-5 text-panel-muted">
                  Important alerts, system updates, and data issues
                </p>
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
                <button
                  type="button"
                  className={cn(
                    "inline-flex h-9 items-center justify-center rounded-pill border px-3 text-sm font-semibold transition",
                    unreadOnly
                      ? "border-brand bg-brand text-white"
                      : "border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] text-panel-copy",
                  )}
                  onClick={() => setUnreadOnly((currentValue) => !currentValue)}
                >
                  Unread only
                </button>
              </div>

              <div className="mt-5 max-h-[26rem] space-y-5 overflow-y-auto pr-1">
                {topbarQuery.isPending ? (
                  <p className="text-sm text-panel-muted">Loading notifications...</p>
                ) : drawerNotifications.length ? (
                  <div className="space-y-3">
                    {drawerNotifications.map((drawerItem) => {
                      const item = drawerItem.kind === "single" ? drawerItem.notification : drawerItem.items[0];
                      const level =
                        item.severity === "CRITICAL" ? "critical" : item.severity === "WARNING" ? "warning" : "info";
                      const primaryActionLabel =
                        drawerItem.kind === "group" ? "Review system state" : getNotificationPrimaryActionLabel(item);
                      const newIds =
                        drawerItem.kind === "group"
                          ? drawerItem.items.filter((notification) => notification.state === "NEW").map((notification) => notification.public_id)
                          : item.state === "NEW"
                            ? [item.public_id]
                            : [];
                      const dismissibleIds =
                        drawerItem.kind === "group"
                          ? drawerItem.items
                              .filter(
                                (notification) =>
                                  notification.dismissible &&
                                  notification.state !== "DISMISSED" &&
                                  notification.state !== "RESOLVED",
                              )
                              .map((notification) => notification.public_id)
                          : item.dismissible && item.state !== "DISMISSED" && item.state !== "RESOLVED"
                            ? [item.public_id]
                            : [];
                      const isGroupExpanded =
                        drawerItem.kind === "group" ? Boolean(expandedNotificationGroups[drawerItem.id]) : false;

                      return (
                      <div
                        key={drawerItem.id}
                        className={cn(
                          "block rounded-[1.2rem] border px-5 py-4 transition",
                          level === "critical" &&
                            "border-[color-mix(in_srgb,var(--danger)_18%,white)] bg-[color-mix(in_srgb,var(--danger)_8%,white)] hover:border-[color:var(--danger)]/35 dark:border-[color-mix(in_srgb,var(--danger)_26%,transparent)] dark:bg-[color-mix(in_srgb,var(--danger)_12%,transparent)]",
                          level === "warning" &&
                            "border-[color-mix(in_srgb,var(--warning)_18%,white)] bg-[color-mix(in_srgb,var(--warning)_8%,white)] hover:border-[color:var(--warning)]/35 dark:border-[color-mix(in_srgb,var(--warning)_26%,transparent)] dark:bg-[color-mix(in_srgb,var(--warning)_12%,transparent)]",
                          level === "info" &&
                            "border-panel-table-wrap bg-[color-mix(in_srgb,var(--dashboard-table-line)_18%,transparent)] hover:border-[var(--dashboard-icon-button-border)]",
                          drawerItem.kind === "group" &&
                            "relative overflow-hidden border-[color-mix(in_srgb,var(--warning)_24%,white)] bg-[linear-gradient(135deg,color-mix(in_srgb,var(--warning)_10%,transparent),color-mix(in_srgb,var(--dashboard-table-line)_12%,transparent))]",
                          item.state === "RESOLVED" && "opacity-70",
                          item.state === "DISMISSED" && "opacity-55",
                        )}
                      >
                        {drawerItem.kind === "group" ? (
                          <div className="pointer-events-none absolute inset-y-0 left-0 w-1 rounded-l-[1.2rem] bg-[color:var(--warning)]/80" />
                        ) : null}
                        <div className="grid grid-cols-[minmax(0,1fr)_auto] items-start gap-x-4 gap-y-2">
                          <div className="min-w-0">
                            {drawerItem.kind === "group" ? (
                              <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-[color-mix(in_srgb,var(--warning)_22%,transparent)] bg-[color-mix(in_srgb,var(--warning)_10%,transparent)] px-2.5 py-1 text-[0.68rem] font-semibold uppercase tracking-[0.14em] text-[color:var(--warning)]">
                                <Waves className="size-3.5" aria-hidden="true" />
                                System health
                              </div>
                            ) : null}
                            <strong className="block text-sm font-semibold leading-6 text-panel-strong">
                              {drawerItem.kind === "group" ? drawerItem.title : item.title}
                            </strong>
                            <p
                              className="mt-1 text-sm leading-6 text-panel-copy"
                              style={{
                                display: "-webkit-box",
                                WebkitLineClamp: 2,
                                WebkitBoxOrient: "vertical",
                                overflow: "hidden",
                              }}
                            >
                              {drawerItem.kind === "group" ? drawerItem.body : getNotificationCardBody(item)}
                            </p>
                          </div>
                          <span
                            title={new Date(drawerItem.kind === "group" ? drawerItem.createdAt : item.created_at).toLocaleString()}
                            className={cn(
                              "max-w-[11rem] text-right text-[0.7rem] font-semibold uppercase tracking-[0.14em]",
                              level === "critical" && "text-[color:var(--danger)]",
                              level === "warning" && "text-[color:var(--warning)]",
                              level === "info" && "text-panel-subtle",
                            )}
                          >
                            {formatRelativeTimestamp(drawerItem.kind === "group" ? drawerItem.createdAt : item.created_at)}
                          </span>
                        </div>
                        {drawerItem.kind === "group" ? (
                          <div className="mt-3">
                            <button
                              type="button"
                              className="inline-flex items-center gap-2 rounded-full border border-panel-table-wrap/80 bg-[color-mix(in_srgb,var(--dashboard-table-line)_12%,transparent)] px-3 py-1.5 text-[0.72rem] font-semibold uppercase tracking-[0.14em] text-panel-copy transition hover:border-[var(--dashboard-icon-button-border)] hover:text-panel-strong"
                              onClick={() =>
                                setExpandedNotificationGroups((currentValue) => ({
                                  ...currentValue,
                                  [drawerItem.id]: !currentValue[drawerItem.id],
                                }))
                              }
                            >
                              {isGroupExpanded ? <ChevronUp className="size-3.5" aria-hidden="true" /> : <ChevronDown className="size-3.5" aria-hidden="true" />}
                              {isGroupExpanded ? "Hide details" : `Show ${drawerItem.items.length} details`}
                            </button>
                            {isGroupExpanded ? (
                              <div className="mt-3 space-y-2 rounded-[1rem] border border-panel-table-wrap/80 bg-[color-mix(in_srgb,var(--dashboard-table-line)_12%,transparent)] px-3 py-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.02)]">
                                {drawerItem.items.map((notification) => (
                                  <div
                                    key={notification.public_id}
                                    className="flex items-start justify-between gap-3 rounded-[0.9rem] border border-transparent px-2 py-2 text-xs transition hover:border-panel-table-wrap/70 hover:bg-[color-mix(in_srgb,var(--dashboard-table-line)_14%,transparent)]"
                                  >
                                    <div className="min-w-0">
                                      <p className="font-medium text-panel-strong">{notification.title}</p>
                                      <p className="mt-1 text-panel-muted">{getNotificationCardBody(notification)}</p>
                                    </div>
                                    <span
                                      title={new Date(notification.created_at).toLocaleString()}
                                      className="shrink-0 text-panel-subtle"
                                    >
                                      {formatRelativeTimestamp(notification.created_at)}
                                    </span>
                                  </div>
                                ))}
                              </div>
                            ) : null}
                          </div>
                        ) : null}
                        <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-2">
                          {primaryActionLabel && (drawerItem.kind === "group" ? drawerItem.href : item.href) ? (
                            <Link
                              href={drawerItem.kind === "group" ? drawerItem.href : item.href}
                              className="text-[0.72rem] font-semibold uppercase tracking-[0.14em] text-brand"
                              onClick={() => {
                                setOpenPanel(null);
                              }}
                            >
                              {primaryActionLabel}
                            </Link>
                          ) : null}
                          {drawerItem.kind === "single" && item.state !== "NEW" ? (
                            <StatusBadge
                              tone={
                                item.state === "ACKNOWLEDGED"
                                  ? "success"
                                  : item.state === "RESOLVED"
                                    ? "success"
                                    : item.state === "DISMISSED"
                                      ? "default"
                                      : item.state === "SEEN"
                                        ? "warning"
                                        : "info"
                              }
                              className="px-3 py-1 tracking-[0.14em]"
                            >
                              {item.state.replaceAll("_", " ")}
                            </StatusBadge>
                          ) : null}
                          {drawerItem.kind === "single" &&
                          item.requires_acknowledgement &&
                          item.state !== "ACKNOWLEDGED" &&
                          item.state !== "RESOLVED" ? (
                            <button
                              type="button"
                              className="text-[0.72rem] font-semibold uppercase tracking-[0.14em] text-brand"
                              onClick={() => {
                                void handleNotificationAcknowledge(item.public_id);
                              }}
                            >
                              Acknowledge
                            </button>
                          ) : newIds.length ? (
                            <button
                              type="button"
                              className="text-[0.72rem] font-semibold uppercase tracking-[0.14em] text-brand"
                              onClick={() => {
                                void handleNotificationsSeen(newIds);
                              }}
                            >
                              Mark seen
                            </button>
                          ) : null}
                          {dismissibleIds.length ? (
                            <div className="relative ml-auto">
                              <button
                                type="button"
                                aria-label={drawerItem.kind === "group" ? "More actions for grouped notifications" : `More actions for ${item.title}`}
                                className="inline-flex size-7 items-center justify-center rounded-full border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] text-panel-subtle transition hover:border-[var(--dashboard-icon-button-border)] hover:text-panel-copy"
                                onClick={() =>
                                  setOpenOverflowMenuId((currentValue) =>
                                    currentValue === drawerItem.id ? null : drawerItem.id,
                                  )
                                }
                              >
                                <Ellipsis className="size-4" aria-hidden="true" />
                              </button>
                              {openOverflowMenuId === drawerItem.id ? (
                                <div className="absolute right-0 top-[calc(100%+0.4rem)] z-30 min-w-[10rem] rounded-[0.9rem] border border-panel-table-wrap bg-[var(--dashboard-topbar-surface)] p-1 shadow-panel">
                                  <button
                                    type="button"
                                    className="flex w-full items-center rounded-[0.7rem] px-3 py-2 text-left text-xs font-medium text-panel-copy transition hover:bg-[color-mix(in_srgb,var(--dashboard-table-line)_20%,transparent)]"
                                    onClick={() => {
                                      setOpenOverflowMenuId(null);
                                      void handleNotificationsDismiss(dismissibleIds);
                                    }}
                                  >
                                    Dismiss
                                  </button>
                                </div>
                              ) : null}
                            </div>
                          ) : null}
                        </div>
                      </div>
                    );})}
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
