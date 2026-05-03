"use client";

import {
  AlertTriangle,
  BellRing,
  Clock3,
  CloudRain,
  DatabaseZap,
  Logs,
  RefreshCcw,
  ShieldAlert,
  ShieldCheck,
  Siren,
  Waves,
  Waypoints,
} from "lucide-react";
import { useMemo, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { DashboardTopbar } from "@/components/dashboard-topbar";
import { RoleGate } from "@/components/role-gate";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { PageSectionHeader } from "@/components/ui/page-section-header";
import { StatusBanner } from "@/components/ui/status-banner";
import { StatusBadge } from "@/components/ui/status-badge";
import { cn } from "@/lib/cn";
import {
  retrySystemBackgroundJobsViaBff,
  runManualRiskScoringViaBff,
  setAlertDeliveryPauseViaBff,
} from "@/lib/dashboard";
import { useSystemQuery } from "@/queries/use-system-query";

function formatRelativeLabel(timestamp: string | null) {
  if (!timestamp) {
    return "No timestamp visible";
  }

  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) {
    return "Invalid timestamp";
  }

  const minutes = Math.max(0, Math.round((Date.now() - date.getTime()) / 60000));

  if (minutes < 1) return "Just now";
  if (minutes < 60) return `${minutes}m ago`;

  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;

  const days = Math.round(hours / 24);
  return `${days}d ago`;
}

function formatEventTime(timestamp: string | null) {
  if (!timestamp) {
    return "--:--";
  }

  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) {
    return "--:--";
  }

  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function formatDateTimeLabel(timestamp: string | null) {
  if (!timestamp) {
    return "No expiry recorded";
  }

  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) {
    return "Invalid expiry";
  }

  return date.toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
}

type SystemTone = "success" | "warning" | "danger" | "default";

function describeFreshness(timestamp: string | null, thresholdMinutes: number) {
  if (!timestamp) {
    return {
      label: "No visible timestamp available",
      detail: "Awaiting visible records",
      isMissing: true,
      isStale: false,
      state: "NO_VISIBLE_TIMESTAMP" as const,
      tone: "default" as const,
    };
  }

  const value = new Date(timestamp).getTime();
  if (Number.isNaN(value)) {
    return {
      label: "Invalid timestamp",
      detail: "Timestamp cannot be read",
      isMissing: true,
      isStale: false,
      state: "INVALID_TIMESTAMP" as const,
      tone: "default" as const,
    };
  }

  const ageMinutes = Math.max(0, Math.round((Date.now() - value) / 60000));

  if (ageMinutes > thresholdMinutes * 2) {
    return {
      label: `${formatRelativeLabel(timestamp)} update`,
      detail: "Older visible data",
      isMissing: false,
      isStale: true,
      state: "OLDER_VISIBLE_DATA" as const,
      tone: "warning" as const,
    };
  }

  if (ageMinutes > thresholdMinutes) {
    return {
      label: `${formatRelativeLabel(timestamp)} update`,
      detail: "Older than target window",
      isMissing: false,
      isStale: true,
      state: "OLDER_THAN_TARGET" as const,
      tone: "warning" as const,
    };
  }

  return {
    label: `${formatRelativeLabel(timestamp)} update`,
    detail: "Within target window",
    isMissing: false,
    isStale: false,
    state: "WITHIN_WINDOW" as const,
    tone: "success" as const,
  };
}

type FreshnessDescription = ReturnType<typeof describeFreshness>;

function getConfidenceQualifier(freshness: FreshnessDescription) {
  if (freshness.isMissing) {
    return "Low confidence: no visible timestamp";
  }
  if (freshness.isStale) {
    return "Low confidence: older visible data";
  }
  return null;
}

function getFreshnessStateLabel(freshness: FreshnessDescription) {
  if (freshness.state === "NO_VISIBLE_TIMESTAMP") {
    return "No visible timestamp";
  }
  if (freshness.state === "INVALID_TIMESTAMP") {
    return "Timestamp unreadable";
  }
  if (freshness.state === "WITHIN_WINDOW") {
    return "Current visible data";
  }
  return "Older visible data";
}

function getSystemStatus({
  riskFreshness,
  alertFreshness,
  facilityFreshness,
  chvFreshness,
  failedAlerts,
  alertBacklog,
}: {
  riskFreshness: FreshnessDescription;
  alertFreshness: FreshnessDescription;
  facilityFreshness: FreshnessDescription;
  chvFreshness: FreshnessDescription;
  failedAlerts: number;
  alertBacklog: number;
}) {
  const freshnessItems = [riskFreshness, alertFreshness, facilityFreshness, chvFreshness];
  const hasMissingTimestamp = freshnessItems.some((item) => item.isMissing);
  const hasStaleVisibleData = freshnessItems.some((item) => item.isStale);

  if (failedAlerts > 0) {
    return {
      state: "DEGRADED" as const,
      label: "System status: Degraded",
      detail: "Visible alert records include failed deliveries. Review alert delivery records before treating the system as calm.",
      tone: "danger" as SystemTone,
    };
  }

  if (hasMissingTimestamp) {
    return {
      state: "DATA_INCOMPLETE" as const,
      label: "System status: Data incomplete",
      detail:
        alertBacklog > 0
          ? "Some dashboard signals are missing visible timestamps, and visible alert records also include queued or retry-pending items. Use this view as operational visibility from dashboard records, not a full health monitor."
          : "Some dashboard signals are missing visible timestamps. Use this view as operational visibility from dashboard records, not a full health monitor.",
      tone: "default" as SystemTone,
    };
  }

  if (hasStaleVisibleData) {
    return {
      state: "STALE_DATA" as const,
      label: "System status: Stale data",
      detail: "Some dashboard-backed records are older than their target freshness window.",
      tone: "warning" as SystemTone,
    };
  }

  if (alertBacklog > 0) {
    return {
      state: "REVIEW_NEEDED" as const,
      label: "System status: Review needed",
      detail: "Visible alert records include queued or retry-pending items. Review alert delivery before treating the view as calm.",
      tone: "warning" as SystemTone,
    };
  }

  return {
    state: "OK" as const,
    label: "System status: OK",
    detail: "Dashboard-backed records are visible and within target freshness windows.",
    tone: "success" as SystemTone,
  };
}

type SystemEvent = {
  time: string | null;
  level: "INFO" | "WARN" | "ERROR";
  message: string;
  tone: "success" | "warning" | "danger";
};

function makeEvent(event: SystemEvent) {
  return event;
}

function getActionErrorMessage(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback;
}

export default function SystemPage() {
  const { currentUser } = useAuth();
  const systemQuery = useSystemQuery({ enabled: Boolean(currentUser) });
  const [controlAction, setControlAction] = useState<"retry" | "risk" | "pause" | null>(null);
  const [controlFeedback, setControlFeedback] = useState<{
    tone: "success" | "danger" | "info" | "warning";
    message: string;
  } | null>(null);
  const snapshot = systemQuery.data ?? null;
  const isLoading = systemQuery.isPending;
  const isRefreshing = systemQuery.isFetching;
  const error = systemQuery.error instanceof Error ? systemQuery.error.message : null;
  const controlStatus = snapshot?.controlStatus ?? null;

  const riskFreshness = describeFreshness(snapshot?.latestRiskTimestamp ?? null, 360);
  const alertFreshness = describeFreshness(snapshot?.latestAlertTimestamp ?? null, 15);
  const facilityFreshness = describeFreshness(snapshot?.latestFacilityTimestamp ?? null, 1440);
  const chvFreshness = describeFreshness(snapshot?.latestChvTimestamp ?? null, 180);
  const alertBacklog = (snapshot?.queuedAlerts ?? 0) + (snapshot?.retryPendingAlerts ?? 0);
  const alertDeliveryPaused = controlStatus?.alert_delivery_paused ?? false;
  const controlDisabled = controlAction !== null || !controlStatus;
  const controlStatusTone = controlStatus ? "success" : error ? "danger" : "default";
  const controlStatusLabel = controlStatus ? "Contracts active" : error ? "Unavailable" : "Loading";
  const systemStatus = getSystemStatus({
    riskFreshness,
    alertFreshness,
    facilityFreshness,
    chvFreshness,
    failedAlerts: snapshot?.failedAlerts ?? 0,
    alertBacklog,
  });
  const riskConfidenceQualifier = getConfidenceQualifier(riskFreshness);
  const alertConfidenceQualifier = getConfidenceQualifier(alertFreshness);
  const facilityConfidenceQualifier = getConfidenceQualifier(facilityFreshness);
  const chvConfidenceQualifier = getConfidenceQualifier(chvFreshness);
  const lastUpdatedLabel = isRefreshing
    ? "Refreshing..."
    : formatRelativeLabel(
        snapshot?.latestAlertTimestamp ??
          snapshot?.latestChvTimestamp ??
          snapshot?.latestRiskTimestamp ??
          snapshot?.latestFacilityTimestamp ??
          null,
      );

  async function handleRetryBackgroundJobs() {
    setControlAction("retry");
    setControlFeedback(null);
    try {
      const result = await retrySystemBackgroundJobsViaBff({ limit: 25 });
      setControlFeedback({
        tone: "success",
        message: `${result.queued_alert_delivery_count} alert delivery retry tasks were queued.`,
      });
      await systemQuery.refetch();
    } catch (actionError) {
      setControlFeedback({
        tone: "danger",
        message: getActionErrorMessage(actionError, "Unable to queue background retry controls."),
      });
    } finally {
      setControlAction(null);
    }
  }

  async function handleManualRiskScoring() {
    setControlAction("risk");
    setControlFeedback(null);
    try {
      const month = new Date().getMonth() + 1;
      const result = await runManualRiskScoringViaBff({
        month,
        trigger_alerts: false,
        send_sms: false,
      });
      setControlFeedback({
        tone: "success",
        message: `Manual risk scoring was queued as task ${result.task_id}.`,
      });
      await systemQuery.refetch();
    } catch (actionError) {
      setControlFeedback({
        tone: "danger",
        message: getActionErrorMessage(actionError, "Unable to queue manual risk scoring."),
      });
    } finally {
      setControlAction(null);
    }
  }

  async function handleAlertDeliveryPause() {
    const nextPausedState = !alertDeliveryPaused;
    setControlAction("pause");
    setControlFeedback(null);
    try {
      const result = await setAlertDeliveryPauseViaBff({
        paused: nextPausedState,
        duration_minutes: 60,
        reason: nextPausedState ? "Paused from system page." : "Resumed from system page.",
      });
      setControlFeedback({
        tone: nextPausedState ? "warning" : "success",
        message: result.alert_delivery_paused
          ? `Alert delivery is paused until ${formatDateTimeLabel(result.alert_delivery_paused_until)}.`
          : "Alert delivery has resumed.",
      });
      await systemQuery.refetch();
    } catch (actionError) {
      setControlFeedback({
        tone: "danger",
        message: getActionErrorMessage(actionError, "Unable to update alert delivery pause."),
      });
    } finally {
      setControlAction(null);
    }
  }

  const statusCards = useMemo(
    () => [
      {
        title: "Visible Wards",
        value: isLoading ? "..." : `${snapshot?.visibleWards ?? 0}`,
        detail: `${snapshot?.wardsWithFreshRisk ?? 0} wards with visible risk timestamps`,
        tone: "info" as const,
        icon: <CloudRain className="size-5" aria-hidden="true" />,
      },
      {
        title: "High-Risk Wards",
        value: isLoading ? "..." : `${snapshot?.highRiskWards ?? 0}`,
        detail: riskConfidenceQualifier ?? "From visible ward risk classifications",
        tone:
          riskFreshness.isMissing
            ? ("default" as const)
            : riskFreshness.isStale
              ? ("warning" as const)
              : (snapshot?.highRiskWards ?? 0) > 0
                ? ("warning" as const)
                : ("success" as const),
        icon: <Siren className="size-5" aria-hidden="true" />,
      },
      {
        title: "Alert Backlog",
        value: isLoading ? "..." : `${alertBacklog}`,
        detail: alertConfidenceQualifier ?? `${snapshot?.failedAlerts ?? 0} failed deliveries in visible records`,
        tone:
          (snapshot?.failedAlerts ?? 0) > 0
            ? ("danger" as const)
            : alertFreshness.isMissing
              ? ("default" as const)
              : alertFreshness.isStale || alertBacklog > 0
                ? ("warning" as const)
                : ("success" as const),
        icon: <BellRing className="size-5" aria-hidden="true" />,
      },
      {
        title: "CHV Sync Summary",
        value: isLoading ? "..." : `${snapshot?.onlineChvs ?? 0}/${snapshot?.activeChvs ?? 0}`,
        detail: chvConfidenceQualifier ?? `${snapshot?.delayedChvs ?? 0} delayed, ${snapshot?.offlineChvs ?? 0} offline in visible CHV records`,
        tone:
          chvFreshness.isMissing
            ? ("default" as const)
            : chvFreshness.isStale || (snapshot?.offlineChvs ?? 0) > 0
              ? ("warning" as const)
              : ("success" as const),
        icon: <ShieldCheck className="size-5" aria-hidden="true" />,
      },
    ],
    [
      alertBacklog,
      isLoading,
      snapshot?.activeChvs,
      snapshot?.delayedChvs,
      snapshot?.failedAlerts,
      snapshot?.highRiskWards,
      snapshot?.offlineChvs,
      snapshot?.onlineChvs,
      snapshot?.visibleWards,
      snapshot?.wardsWithFreshRisk,
      alertConfidenceQualifier,
      chvConfidenceQualifier,
      alertFreshness.isMissing,
      alertFreshness.isStale,
      chvFreshness.isMissing,
      chvFreshness.isStale,
      riskConfidenceQualifier,
      riskFreshness.isMissing,
      riskFreshness.isStale,
    ],
  );

  const freshnessFeeds = useMemo(
    () => [
      {
        title: "Risk Scoring Feed",
        evidence: `${snapshot?.wardsWithFreshRisk ?? 0}/${snapshot?.visibleWards ?? 0} ward risk records expose generated timestamps`,
        status: riskFreshness.label,
        detail: riskFreshness.detail,
        stateLabel: getFreshnessStateLabel(riskFreshness),
        lastVisible: snapshot?.latestRiskTimestamp ? `Last visible: ${formatRelativeLabel(snapshot.latestRiskTimestamp)}` : "No last visible timestamp",
        tone: riskFreshness.tone,
        icon: <CloudRain className="size-4" aria-hidden="true" />,
      },
      {
        title: "Alert Delivery Feed",
        evidence: `${snapshot?.visibleAlerts ?? 0} alert records visible; ${alertBacklog} queued or retry-pending`,
        status:
          (snapshot?.failedAlerts ?? 0) > 0
            ? `${snapshot?.failedAlerts ?? 0} failed delivery records`
            : alertFreshness.label,
        detail: (snapshot?.failedAlerts ?? 0) > 0 ? "Visible delivery failure" : alertFreshness.detail,
        stateLabel: (snapshot?.failedAlerts ?? 0) > 0 ? "Delivery failure" : getFreshnessStateLabel(alertFreshness),
        lastVisible: snapshot?.latestAlertTimestamp ? `Last visible: ${formatRelativeLabel(snapshot.latestAlertTimestamp)}` : "No last visible timestamp",
        tone: (snapshot?.failedAlerts ?? 0) > 0 ? ("danger" as const) : alertFreshness.tone,
        icon: <BellRing className="size-4" aria-hidden="true" />,
      },
      {
        title: "Facility Registry",
        evidence: `${snapshot?.visibleFacilities ?? 0} facility records visible`,
        status: facilityFreshness.label,
        detail: facilityFreshness.detail,
        stateLabel: getFreshnessStateLabel(facilityFreshness),
        lastVisible: snapshot?.latestFacilityTimestamp ? `Last visible: ${formatRelativeLabel(snapshot.latestFacilityTimestamp)}` : "No last visible timestamp",
        tone: facilityFreshness.tone,
        icon: <DatabaseZap className="size-4" aria-hidden="true" />,
      },
      {
        title: "CHV Operations Feed",
        evidence: `${snapshot?.syncPayloads24h ?? 0} sync payloads and ${snapshot?.ussdSessions24h ?? 0} USSD sessions in the last 24h`,
        status: chvFreshness.label,
        detail: chvFreshness.detail,
        stateLabel: getFreshnessStateLabel(chvFreshness),
        lastVisible: snapshot?.latestChvTimestamp ? `Last visible: ${formatRelativeLabel(snapshot.latestChvTimestamp)}` : "No last visible timestamp",
        tone: chvFreshness.tone,
        icon: <Waves className="size-4" aria-hidden="true" />,
      },
    ],
    [
      alertBacklog,
      alertFreshness.detail,
      alertFreshness.label,
      alertFreshness.state,
      alertFreshness.tone,
      chvFreshness.detail,
      chvFreshness.label,
      chvFreshness.state,
      chvFreshness.tone,
      facilityFreshness.detail,
      facilityFreshness.label,
      facilityFreshness.state,
      facilityFreshness.tone,
      riskFreshness.detail,
      riskFreshness.label,
      riskFreshness.state,
      riskFreshness.tone,
      snapshot?.failedAlerts,
      snapshot?.latestAlertTimestamp,
      snapshot?.latestChvTimestamp,
      snapshot?.latestFacilityTimestamp,
      snapshot?.latestRiskTimestamp,
      snapshot?.syncPayloads24h,
      snapshot?.ussdSessions24h,
      snapshot?.visibleAlerts,
      snapshot?.visibleFacilities,
      snapshot?.visibleWards,
      snapshot?.wardsWithFreshRisk,
    ],
  );

  const observedChannels = useMemo(
    () => [
      {
        group: "Alert delivery records",
        name:
          snapshot?.deliveryBackends.length
            ? snapshot.deliveryBackends
                .slice(0, 2)
                .map((item) => item.name)
                .join(", ")
            : "No delivery records observed",
        note: snapshot?.deliveryBackends.length
          ? `${snapshot.deliveryBackends.reduce((sum, item) => sum + item.count, 0)} alerts sampled through delivery metadata`
          : "Awaiting alert activity",
        tone: snapshot?.deliveryBackends.length ? ("success" as const) : ("default" as const),
        icon: <Waypoints className="size-4" aria-hidden="true" />,
      },
      {
        group: "CHV submissions (24h)",
        name: `${snapshot?.syncPayloads24h ?? 0} sync payloads`,
        note: `${snapshot?.triageSessions24h ?? 0} triage sessions and ${snapshot?.referrals24h ?? 0} referrals`,
        tone: (snapshot?.syncPayloads24h ?? 0) > 0 ? ("success" as const) : ("default" as const),
        icon: <Waves className="size-4" aria-hidden="true" />,
      },
      {
        group: "USSD traffic (24h)",
        name: `${snapshot?.ussdSessions24h ?? 0} sessions`,
        note: "From visible USSD session records",
        tone: (snapshot?.ussdSessions24h ?? 0) > 0 ? ("success" as const) : ("default" as const),
        icon: <BellRing className="size-4" aria-hidden="true" />,
      },
      {
        group: "Facility registry",
        name: `${snapshot?.visibleFacilities ?? 0} facility records`,
        note: facilityConfidenceQualifier ?? facilityFreshness.detail,
        tone:
          facilityFreshness.tone === "warning"
            ? ("warning" as const)
            : facilityFreshness.tone === "success"
              ? ("success" as const)
              : ("default" as const),
        icon: <DatabaseZap className="size-4" aria-hidden="true" />,
      },
    ],
    [
      facilityFreshness.detail,
      facilityFreshness.tone,
      facilityConfidenceQualifier,
      snapshot?.deliveryBackends,
      snapshot?.referrals24h,
      snapshot?.syncPayloads24h,
      snapshot?.triageSessions24h,
      snapshot?.ussdSessions24h,
      snapshot?.visibleFacilities,
    ],
  );

  const systemEvents: SystemEvent[] = useMemo(() => {
    const events: Array<SystemEvent | null> = [
      snapshot?.latestRiskTimestamp
        ? makeEvent({
            time: snapshot.latestRiskTimestamp,
            level: "INFO",
            message: `Ward risk record is ${formatRelativeLabel(snapshot.latestRiskTimestamp)} and covers ${snapshot.wardsWithFreshRisk}/${snapshot.visibleWards} visible wards.`,
            tone: "success" as const,
          })
        : null,
      (snapshot?.failedAlerts ?? 0) > 0
        ? makeEvent({
            time: snapshot?.latestFailedAlertTimestamp ?? snapshot?.latestAlertTimestamp ?? null,
            level: "ERROR",
            message: `${snapshot?.failedAlerts ?? 0} alert deliveries are recorded as failed in visible records.`,
            tone: "danger" as const,
          })
        : null,
      (snapshot?.retryPendingAlerts ?? 0) > 0
        ? makeEvent({
            time: snapshot?.latestRetryAlertTimestamp ?? snapshot?.latestAlertTimestamp ?? null,
            level: "WARN",
            message: `${snapshot?.retryPendingAlerts ?? 0} alerts are recorded as retry-pending in visible records.`,
            tone: "warning" as const,
          })
        : null,
      snapshot?.latestChvTimestamp
        ? makeEvent({
            time: snapshot.latestChvTimestamp,
            level: "INFO",
            message: `CHV record landed ${formatRelativeLabel(snapshot.latestChvTimestamp)} across sync, triage, and USSD traces.`,
            tone: chvFreshness.isStale ? ("warning" as const) : ("success" as const),
          })
        : null,
      snapshot?.latestFacilityTimestamp
        ? makeEvent({
            time: snapshot.latestFacilityTimestamp,
            level: facilityFreshness.isStale ? "WARN" : "INFO",
            message: `Facility registry was last updated ${formatRelativeLabel(snapshot.latestFacilityTimestamp)} for ${snapshot.visibleFacilities} visible facilities.`,
            tone: facilityFreshness.isStale ? ("warning" as const) : ("success" as const),
          })
        : null,
      alertBacklog > 0
        ? makeEvent({
            time: snapshot?.latestAlertTimestamp ?? null,
            level: "INFO",
            message: `${alertBacklog} alerts are recorded as queued or retry-pending in visible records.`,
            tone: "warning" as const,
          })
        : null,
    ];

    const filteredEvents = events.filter((event): event is SystemEvent => event !== null);
    filteredEvents.sort((left, right) => {
      const leftTime = left.time ? new Date(left.time).getTime() : 0;
      const rightTime = right.time ? new Date(right.time).getTime() : 0;
      return rightTime - leftTime;
    });

    return filteredEvents.slice(0, 6);
  }, [
    alertBacklog,
    chvFreshness.isStale,
    facilityFreshness.isStale,
    snapshot?.failedAlerts,
    snapshot?.latestAlertTimestamp,
    snapshot?.latestChvTimestamp,
    snapshot?.latestFailedAlertTimestamp,
    snapshot?.latestFacilityTimestamp,
    snapshot?.latestRetryAlertTimestamp,
    snapshot?.latestRiskTimestamp,
    snapshot?.retryPendingAlerts,
    snapshot?.visibleFacilities,
    snapshot?.visibleWards,
    snapshot?.wardsWithFreshRisk,
  ]);

  if (!currentUser) {
    return null;
  }

  return (
    <div className="space-y-6">
      <DashboardTopbar
        title="System Status"
        subtitle="System status and explicit control contracts"
        lastUpdatedLabel={lastUpdatedLabel}
        lastUpdatedTone={
          systemStatus.state !== "OK" &&
          (riskFreshness.isStale || alertFreshness.isStale || facilityFreshness.isStale || chvFreshness.isStale)
            ? "stale"
            : "default"
        }
        onRefresh={() => {
          void systemQuery.refetch();
        }}
      />

      <RoleGate
        allowedRoles={["ADMIN", "ANALYST"]}
        title="System page is role-restricted"
        message="Only Admin and Analyst roles should access this read-only system status page."
      >
        {error ? (
          <StatusBanner tone="danger" icon={<AlertTriangle aria-hidden="true" />}>
            {error}
          </StatusBanner>
        ) : null}

        <Card
          className={cn(
            "rounded-[2rem] px-5 py-5 sm:px-6",
            systemStatus.tone === "success" &&
              "border-[color-mix(in_srgb,var(--success)_24%,transparent)] bg-[color-mix(in_srgb,var(--success)_7%,var(--panel))]",
            systemStatus.tone === "warning" &&
              "border-[color-mix(in_srgb,var(--warning)_28%,transparent)] bg-[color-mix(in_srgb,var(--warning)_8%,var(--panel))]",
            systemStatus.tone === "danger" &&
              "border-[color-mix(in_srgb,var(--danger)_28%,transparent)] bg-[color-mix(in_srgb,var(--danger)_8%,var(--panel))]",
            systemStatus.tone === "default" &&
              "border-[color-mix(in_srgb,var(--dashboard-subtle-copy)_24%,transparent)] bg-[color-mix(in_srgb,var(--dashboard-subtle-copy)_7%,var(--panel))]",
          )}
        >
          <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
            <div className="flex items-start gap-4">
              <span
                className={cn(
                  "inline-flex size-11 shrink-0 items-center justify-center rounded-2xl",
                  systemStatus.tone === "success" &&
                    "bg-[color-mix(in_srgb,var(--success)_16%,transparent)] text-[color:var(--success)]",
                  systemStatus.tone === "warning" &&
                    "bg-[color-mix(in_srgb,var(--warning)_16%,transparent)] text-[color:var(--warning)]",
                  systemStatus.tone === "danger" &&
                    "bg-[color-mix(in_srgb,var(--danger)_16%,transparent)] text-[color:var(--danger)]",
                  systemStatus.tone === "default" &&
                    "bg-[color-mix(in_srgb,var(--dashboard-subtle-copy)_15%,transparent)] text-panel-muted",
                )}
              >
                {systemStatus.tone === "success" ? (
                  <ShieldCheck className="size-5" aria-hidden="true" />
                ) : systemStatus.tone === "danger" ? (
                  <AlertTriangle className="size-5" aria-hidden="true" />
                ) : systemStatus.tone === "warning" ? (
                  <Clock3 className="size-5" aria-hidden="true" />
                ) : (
                  <DatabaseZap className="size-5" aria-hidden="true" />
                )}
              </span>
              <div>
                <p className="text-[0.68rem] font-semibold uppercase tracking-[0.18em] text-panel-subtle">
                  System status
                </p>
                <h2 className="mt-2 text-2xl font-semibold tracking-[-0.04em] text-panel-strong">
                  {isLoading ? "Checking dashboard records" : systemStatus.label.replace("System status: ", "")}
                </h2>
                <p className="mt-2 max-w-3xl text-sm text-panel-muted">
                  {isLoading ? "Loading visible dashboard-backed records before assigning a status." : systemStatus.detail}
                </p>
              </div>
            </div>
            <StatusBadge
              tone={
                systemStatus.tone === "danger"
                  ? "danger"
                  : systemStatus.tone === "warning"
                    ? "warning"
                    : systemStatus.tone === "success"
                      ? "success"
                      : "default"
              }
              className="w-fit px-3 py-1 tracking-[0.14em]"
            >
              {systemStatus.state.replaceAll("_", " ")}
            </StatusBadge>
          </div>
        </Card>

        <section className="grid gap-4 xl:grid-cols-4">
          {statusCards.map((card) => (
            <Card key={card.title} className="rounded-[1.9rem] px-5 py-5">
              <div className="flex items-start justify-between gap-4">
                <div className="space-y-3">
                  <p className="text-[0.68rem] font-semibold uppercase tracking-[0.18em] text-panel-subtle">
                    {card.title}
                  </p>
                  <div className="space-y-1">
                    <div className="text-[2rem] font-semibold leading-none tracking-[-0.05em] text-panel-strong">
                      {card.value}
                    </div>
                    <p className="text-sm text-panel-muted">{card.detail}</p>
                  </div>
                </div>
                <span
                  className={cn(
                    "inline-flex size-11 items-center justify-center rounded-2xl",
                    card.tone === "success" &&
                      "bg-[color-mix(in_srgb,var(--success)_14%,white)] text-[color:var(--success)] dark:bg-[color-mix(in_srgb,var(--success)_20%,transparent)]",
                    card.tone === "warning" &&
                      "bg-[color-mix(in_srgb,var(--warning)_14%,white)] text-[color:var(--warning)] dark:bg-[color-mix(in_srgb,var(--warning)_20%,transparent)]",
                    card.tone === "danger" &&
                      "bg-[color-mix(in_srgb,var(--danger)_14%,white)] text-[color:var(--danger)] dark:bg-[color-mix(in_srgb,var(--danger)_20%,transparent)]",
                    card.tone === "info" &&
                      "bg-[color-mix(in_srgb,var(--brand)_12%,white)] text-brand dark:bg-[color-mix(in_srgb,var(--brand)_18%,transparent)]",
                  )}
                >
                  {card.icon}
                </span>
              </div>
              <div
                className={cn(
                  "mt-4 h-1.5 rounded-full",
                  card.tone === "success" && "bg-[color-mix(in_srgb,var(--success)_20%,white)]",
                  card.tone === "warning" && "bg-[color-mix(in_srgb,var(--warning)_20%,white)]",
                  card.tone === "danger" && "bg-[color-mix(in_srgb,var(--danger)_20%,white)]",
                  card.tone === "info" && "bg-[color-mix(in_srgb,var(--brand)_20%,white)]",
                )}
              />
            </Card>
          ))}
        </section>

        <section>
          <Card className="rounded-[2rem] px-5 py-5 sm:px-6">
            <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
              <PageSectionHeader
                className="gap-1"
                title="Data Freshness"
                description="These signals are based on visible record timestamps, not live health checks."
              />
              <Button
                variant="secondary"
                className="h-10 rounded-pill px-4"
                onClick={() => {
                  void systemQuery.refetch();
                }}
              >
                <RefreshCcw className="mr-2 size-4" aria-hidden="true" />
                Refresh visible records
              </Button>
            </div>

            <div className="mt-5 space-y-3">
              {freshnessFeeds.map((feed) => (
                <div
                  key={feed.title}
                  className={cn(
                    "flex flex-col gap-3 rounded-[1.35rem] border px-4 py-4 sm:flex-row sm:items-center sm:justify-between",
                    feed.tone === "success" &&
                      "border-[color-mix(in_srgb,var(--success)_18%,white)] bg-[color-mix(in_srgb,var(--success)_8%,white)] dark:border-[color-mix(in_srgb,var(--success)_26%,transparent)] dark:bg-[color-mix(in_srgb,var(--success)_12%,transparent)]",
                    feed.tone === "warning" &&
                      "border-[color-mix(in_srgb,var(--warning)_18%,white)] bg-[color-mix(in_srgb,var(--warning)_8%,white)] dark:border-[color-mix(in_srgb,var(--warning)_26%,transparent)] dark:bg-[color-mix(in_srgb,var(--warning)_12%,transparent)]",
                    feed.tone === "danger" &&
                      "border-[color-mix(in_srgb,var(--danger)_20%,white)] bg-[color-mix(in_srgb,var(--danger)_8%,white)] dark:border-[color-mix(in_srgb,var(--danger)_28%,transparent)] dark:bg-[color-mix(in_srgb,var(--danger)_12%,transparent)]",
                    feed.tone === "default" &&
                      "border-[var(--dashboard-table-line)] bg-[color-mix(in_srgb,var(--dashboard-table-line)_16%,transparent)]",
                  )}
                >
                  <div className="flex items-start gap-3">
                    <span
                      className={cn(
                        "inline-flex size-10 shrink-0 items-center justify-center rounded-2xl",
                        feed.tone === "success" &&
                          "bg-[color-mix(in_srgb,var(--success)_14%,white)] text-[color:var(--success)] dark:bg-[color-mix(in_srgb,var(--success)_20%,transparent)]",
                        feed.tone === "warning" &&
                          "bg-[color-mix(in_srgb,var(--warning)_14%,white)] text-[color:var(--warning)] dark:bg-[color-mix(in_srgb,var(--warning)_20%,transparent)]",
                        feed.tone === "danger" &&
                          "bg-[color-mix(in_srgb,var(--danger)_14%,white)] text-[color:var(--danger)] dark:bg-[color-mix(in_srgb,var(--danger)_20%,transparent)]",
                        feed.tone === "default" &&
                          "bg-[color-mix(in_srgb,var(--dashboard-subtle-copy)_14%,var(--panel))] text-panel-muted",
                      )}
                    >
                      {feed.icon}
                    </span>
                    <div>
                      <strong className="block text-sm font-semibold text-panel-strong">{feed.title}</strong>
                      <p className="mt-1 text-xs text-panel-muted">{feed.evidence}</p>
                      <p className="mt-1 text-[0.68rem] font-medium text-panel-subtle">{feed.lastVisible}</p>
                    </div>
                  </div>

                  <div className="space-y-1 text-right">
                    <div className="text-sm font-semibold text-panel-strong">{feed.status}</div>
                    <div className="text-[0.68rem] font-semibold uppercase tracking-[0.14em] text-panel-subtle">
                      {feed.stateLabel}
                    </div>
                    <div
                      className={cn(
                        "text-[0.68rem] font-semibold uppercase tracking-[0.14em]",
                        feed.tone === "success" && "text-[color:var(--success)]",
                        feed.tone === "warning" && "text-[color:var(--warning)]",
                        feed.tone === "danger" && "text-[color:var(--danger)]",
                        feed.tone === "default" && "text-panel-muted",
                      )}
                    >
                      {feed.detail}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </Card>
        </section>

        <section>
          <Card className="rounded-[2rem] px-5 py-5 sm:px-6">
            <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
              <PageSectionHeader
                className="gap-1"
                title="Observed Activity"
                description="Activity appears only where dashboard-backed records exist."
              />
              <div className="flex flex-wrap items-center gap-2">
                <StatusBadge tone="default" className="px-3 py-1 tracking-[0.14em]">
                  Read-only
                </StatusBadge>
                <StatusBadge tone="default" className="px-3 py-1 tracking-[0.14em]">
                  Dashboard records
                </StatusBadge>
              </div>
            </div>

            <div className="mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
              {observedChannels.map((integration) => (
                <div key={`${integration.group}-${integration.name}`} className="rounded-[1.25rem] border border-panel-table-wrap px-3.5 py-3.5">
                  <div className="flex items-start justify-between gap-3">
                    <span
                      className={cn(
                        "inline-flex size-8 items-center justify-center rounded-xl",
                        integration.tone === "success" &&
                          "bg-[color-mix(in_srgb,var(--success)_14%,white)] text-[color:var(--success)] dark:bg-[color-mix(in_srgb,var(--success)_20%,transparent)]",
                        integration.tone === "warning" &&
                          "bg-[color-mix(in_srgb,var(--warning)_14%,white)] text-[color:var(--warning)] dark:bg-[color-mix(in_srgb,var(--warning)_20%,transparent)]",
                        integration.tone === "default" &&
                          "bg-[color-mix(in_srgb,var(--dashboard-subtle-copy)_14%,var(--panel))] text-panel-muted dark:bg-[color-mix(in_srgb,var(--dashboard-subtle-copy)_18%,transparent)]",
                      )}
                    >
                      {integration.icon}
                    </span>
                    <span
                      className={cn(
                        "mt-1 size-2 rounded-full",
                        integration.tone === "success" && "bg-[color:var(--success)]",
                        integration.tone === "warning" && "bg-[color:var(--warning)]",
                        integration.tone === "default" && "bg-[var(--dashboard-subtle-copy)]",
                      )}
                    />
                  </div>
                  <p className="mt-3 text-[0.65rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle">
                    {integration.group}
                  </p>
                  <strong className="mt-1 block text-sm font-semibold text-panel-strong">{integration.name}</strong>
                  <p
                    className={cn(
                      "mt-2 text-xs font-medium",
                      integration.tone === "success" && "text-[color:var(--success)]",
                      integration.tone === "warning" && "text-[color:var(--warning)]",
                      integration.tone === "default" && "text-panel-muted",
                    )}
                  >
                    {integration.note}
                  </p>
                </div>
              ))}
            </div>

            <div className="mt-6">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="text-[0.68rem] font-semibold uppercase tracking-[0.18em] text-panel-subtle">
                    Latest record summaries
                  </p>
                  <p className="mt-1 text-xs text-panel-muted">Summaries are derived from dashboard records, not raw service logs.</p>
                </div>
                <span className="inline-flex items-center gap-2 text-xs font-medium text-panel-muted">
                  <Logs className="size-4" aria-hidden="true" />
                  {systemEvents.length > 0 ? `${Math.min(systemEvents.length, 5)} visible summaries` : "No visible summaries"}
                </span>
              </div>

              <div className="mt-3 overflow-hidden rounded-[1.4rem] border border-panel-table-wrap">
                <div className="divide-y divide-[var(--dashboard-table-line)]">
                  {systemEvents.length > 0 ? (
                    systemEvents.slice(0, 5).map((event, index) => (
                      <div key={`${event.level}-${index}`} className="grid gap-3 px-4 py-3 md:grid-cols-[4.5rem_5rem_minmax(0,1fr)] md:items-center">
                        <div className="text-xs font-medium text-panel-muted">{formatEventTime(event.time)}</div>
                        <div className="flex items-center gap-2">
                          <span
                            className={cn(
                              "h-7 w-1 rounded-full",
                              event.tone === "success" && "bg-[color:var(--success)]",
                              event.tone === "warning" && "bg-[color:var(--warning)]",
                              event.tone === "danger" && "bg-[color:var(--danger)]",
                            )}
                          />
                          <StatusBadge
                            tone={event.tone === "danger" ? "danger" : event.tone === "warning" ? "warning" : "success"}
                            className="px-2.5 py-1 tracking-[0.14em]"
                          >
                            {event.level}
                          </StatusBadge>
                        </div>
                        <div className="text-sm text-panel-copy">{event.message}</div>
                      </div>
                    ))
                  ) : (
                    <div className="px-4 py-6 text-sm text-panel-muted">No dashboard-backed record summaries are available for this view yet.</div>
                  )}
                </div>
              </div>
            </div>

            <div className="mt-5 flex flex-wrap items-center gap-4 text-sm text-panel-muted">
              <span className="inline-flex items-center gap-2">
                <Clock3 className="size-4" aria-hidden="true" />
                Alert freshness: {alertFreshness.detail}
              </span>
              <span className="inline-flex items-center gap-2">
                <ShieldAlert className="size-4" aria-hidden="true" />
                Control contracts are wired to backend endpoints.
              </span>
            </div>
          </Card>
        </section>

        <section>
          <Card className="rounded-[2rem] px-5 py-5 sm:px-6">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
              <PageSectionHeader
                className="gap-1"
                title="System controls"
                description="Backend contracts are available for retry queues, manual risk scoring, and alert delivery pause."
              />
              <StatusBadge tone={controlStatusTone} className="w-fit px-3 py-1 tracking-[0.14em]">
                {controlStatusLabel}
              </StatusBadge>
            </div>

            {!controlStatus && error ? (
              <StatusBanner tone="danger" className="mt-5" icon={<AlertTriangle aria-hidden="true" />}>
                System controls could not load: {error}
              </StatusBanner>
            ) : null}

            {controlFeedback ? (
              <StatusBanner tone={controlFeedback.tone} className="mt-5">
                {controlFeedback.message}
              </StatusBanner>
            ) : null}

            {alertDeliveryPaused ? (
              <StatusBanner tone="warning" className="mt-5" icon={<ShieldAlert aria-hidden="true" />}>
                Alert delivery is paused until {formatDateTimeLabel(controlStatus?.alert_delivery_paused_until ?? null)}.
              </StatusBanner>
            ) : null}

            <div className="mt-5 grid gap-4 xl:grid-cols-3">
              <div className="rounded-[1.35rem] border border-panel-table-wrap px-4 py-4">
                <div className="flex items-center gap-3">
                  <span className="inline-flex size-9 items-center justify-center rounded-xl bg-[color-mix(in_srgb,var(--success)_14%,white)] text-[color:var(--success)] dark:bg-[color-mix(in_srgb,var(--success)_20%,transparent)]">
                    <RefreshCcw className="size-4" aria-hidden="true" />
                  </span>
                  <h3 className="text-sm font-semibold text-panel-strong">Background retry</h3>
                </div>
                <p className="mt-4 text-sm text-panel-muted">
                  Queues retryable SMS alert delivery jobs from queued and retry-pending records.
                </p>
                <p className="mt-3 text-xs font-semibold uppercase tracking-[0.14em] text-panel-subtle">
                  {alertBacklog} visible queued/retry-pending
                </p>
                <Button
                  variant="secondary"
                  size="sm"
                  className="mt-4"
                  onClick={handleRetryBackgroundJobs}
                  disabled={controlDisabled || !controlStatus?.can_retry_background_jobs}
                >
                  <RefreshCcw className={cn("size-4", controlAction === "retry" && "animate-spin")} aria-hidden="true" />
                  Retry background jobs
                </Button>
              </div>

              <div className="rounded-[1.35rem] border border-panel-table-wrap px-4 py-4">
                <div className="flex items-center gap-3">
                  <span className="inline-flex size-9 items-center justify-center rounded-xl bg-[color-mix(in_srgb,var(--brand)_14%,white)] text-brand dark:bg-[color-mix(in_srgb,var(--brand)_20%,transparent)]">
                    <Siren className="size-4" aria-hidden="true" />
                  </span>
                  <h3 className="text-sm font-semibold text-panel-strong">Manual risk scoring</h3>
                </div>
                <p className="mt-4 text-sm text-panel-muted">
                  Queues a model run for the current month. Alert creation and SMS delivery stay off by default.
                </p>
                <p className="mt-3 text-xs font-semibold uppercase tracking-[0.14em] text-panel-subtle">
                  Governed async model task
                </p>
                <Button
                  variant="secondary"
                  size="sm"
                  className="mt-4"
                  onClick={handleManualRiskScoring}
                  disabled={controlDisabled || !controlStatus?.can_run_manual_risk_scoring}
                >
                  <Siren className="size-4" aria-hidden="true" />
                  Run risk scoring
                </Button>
              </div>

              <div className="rounded-[1.35rem] border border-panel-table-wrap px-4 py-4">
                <div className="flex items-center gap-3">
                  <span
                    className={cn(
                      "inline-flex size-9 items-center justify-center rounded-xl",
                      alertDeliveryPaused
                        ? "bg-[color-mix(in_srgb,var(--warning)_16%,white)] text-[color:var(--warning)] dark:bg-[color-mix(in_srgb,var(--warning)_22%,transparent)]"
                        : "bg-[color-mix(in_srgb,var(--success)_14%,white)] text-[color:var(--success)] dark:bg-[color-mix(in_srgb,var(--success)_20%,transparent)]",
                    )}
                  >
                    <BellRing className="size-4" aria-hidden="true" />
                  </span>
                  <h3 className="text-sm font-semibold text-panel-strong">Alert delivery</h3>
                </div>
                <p className="mt-4 text-sm text-panel-muted">
                  Pauses or resumes outbound SMS delivery while dashboard alerts and records stay visible.
                </p>
                <p className="mt-3 text-xs font-semibold uppercase tracking-[0.14em] text-panel-subtle">
                  {alertDeliveryPaused ? "Paused" : "Active"}
                </p>
                <Button
                  variant={alertDeliveryPaused ? "primary" : "danger"}
                  size="sm"
                  className="mt-4"
                  onClick={handleAlertDeliveryPause}
                  disabled={controlDisabled || !controlStatus?.can_pause_alert_delivery}
                >
                  <BellRing className="size-4" aria-hidden="true" />
                  {alertDeliveryPaused ? "Resume alert delivery" : "Pause alert delivery"}
                </Button>
              </div>
            </div>
          </Card>
        </section>
      </RoleGate>
    </div>
  );
}
