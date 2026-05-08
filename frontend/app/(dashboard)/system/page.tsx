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
    return "No update received yet";
  }

  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) {
    return "Update time unavailable";
  }

  const minutes = Math.max(0, Math.round((Date.now() - date.getTime()) / 60000));

  if (minutes < 1) return "just now";
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
    return "the scheduled time";
  }

  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) {
    return "the scheduled time";
  }

  return date.toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
}

function formatCountLabel(count: number, singular: string, plural = `${singular}s`) {
  return `${count} ${count === 1 ? singular : plural}`;
}

type ReadinessTone = "success" | "warning" | "danger" | "default";

function toneIconSurfaceClasses(tone: ReadinessTone | "info") {
  switch (tone) {
    case "success":
      return "border-[color-mix(in_srgb,var(--success)_24%,var(--dashboard-panel-border))] bg-[color-mix(in_srgb,var(--success)_14%,var(--dashboard-panel-surface))] text-[color:var(--success)]";
    case "warning":
      return "border-[color-mix(in_srgb,var(--warning)_26%,var(--dashboard-panel-border))] bg-[color-mix(in_srgb,var(--warning)_16%,var(--dashboard-panel-surface))] text-[color:var(--warning)]";
    case "danger":
      return "border-[color-mix(in_srgb,var(--danger)_26%,var(--dashboard-panel-border))] bg-[color-mix(in_srgb,var(--danger)_15%,var(--dashboard-panel-surface))] text-[color:var(--danger)]";
    case "info":
      return "border-[color-mix(in_srgb,var(--brand)_24%,var(--dashboard-panel-border))] bg-[color-mix(in_srgb,var(--brand)_14%,var(--dashboard-panel-surface))] text-brand";
    default:
      return "border-[color-mix(in_srgb,var(--dashboard-subtle-copy)_24%,var(--dashboard-panel-border))] bg-[color-mix(in_srgb,var(--dashboard-subtle-copy)_12%,var(--dashboard-panel-surface))] text-panel-muted";
  }
}

function readinessRowSurfaceClasses(tone: ReadinessTone) {
  switch (tone) {
    case "success":
      return "border-[color-mix(in_srgb,var(--success)_26%,var(--dashboard-panel-border))] bg-[color-mix(in_srgb,var(--success)_9%,var(--dashboard-panel-surface))]";
    case "warning":
      return "border-[color-mix(in_srgb,var(--warning)_28%,var(--dashboard-panel-border))] bg-[color-mix(in_srgb,var(--warning)_10%,var(--dashboard-panel-surface))]";
    case "danger":
      return "border-[color-mix(in_srgb,var(--danger)_30%,var(--dashboard-panel-border))] bg-[color-mix(in_srgb,var(--danger)_10%,var(--dashboard-panel-surface))]";
    default:
      return "border-[var(--dashboard-table-line)] bg-[color-mix(in_srgb,var(--dashboard-table-line)_24%,var(--dashboard-panel-surface))]";
  }
}

function describeUpdate(timestamp: string | null, targetMinutes: number) {
  if (!timestamp) {
    return {
      label: "No update received yet",
      detail: "Waiting for an update",
      stateLabel: "Missing",
      isMissing: true,
      isDelayed: false,
      tone: "default" as const,
    };
  }

  const value = new Date(timestamp).getTime();
  if (Number.isNaN(value)) {
    return {
      label: "Update time unavailable",
      detail: "Needs review",
      stateLabel: "Needs review",
      isMissing: true,
      isDelayed: false,
      tone: "default" as const,
    };
  }

  const ageMinutes = Math.max(0, Math.round((Date.now() - value) / 60000));
  const label = `Last updated ${formatRelativeLabel(timestamp)}`;

  if (ageMinutes > targetMinutes * 2) {
    return {
      label,
      detail: "Delayed",
      stateLabel: "Delayed",
      isMissing: false,
      isDelayed: true,
      tone: "warning" as const,
    };
  }

  if (ageMinutes > targetMinutes) {
    return {
      label,
      detail: "Later than expected",
      stateLabel: "Delayed",
      isMissing: false,
      isDelayed: true,
      tone: "warning" as const,
    };
  }

  return {
    label,
    detail: "On time",
    stateLabel: "Current",
    isMissing: false,
    isDelayed: false,
    tone: "success" as const,
  };
}

type UpdateDescription = ReturnType<typeof describeUpdate>;

function getUpdateNote(update: UpdateDescription) {
  if (update.isMissing) {
    return "Update not received yet";
  }

  if (update.isDelayed) {
    return "Update later than expected";
  }

  return null;
}

function getReadinessStatus({
  riskUpdate,
  alertUpdate,
  facilityUpdate,
  chvUpdate,
  failedAlerts,
  alertsWaiting,
}: {
  riskUpdate: UpdateDescription;
  alertUpdate: UpdateDescription;
  facilityUpdate: UpdateDescription;
  chvUpdate: UpdateDescription;
  failedAlerts: number;
  alertsWaiting: number;
}) {
  const updates = [riskUpdate, alertUpdate, facilityUpdate, chvUpdate];
  const hasMissingUpdate = updates.some((item) => item.isMissing);
  const hasDelayedUpdate = updates.some((item) => item.isDelayed);

  if (failedAlerts > 0) {
    return {
      state: "needs_attention" as const,
      label: "Needs attention",
      detail: "Some alerts did not send. Review alert sending before relying on the dashboard for decisions.",
      badgeLabel: "Review alert sending",
      tone: "danger" as ReadinessTone,
    };
  }

  if (hasMissingUpdate) {
    return {
      state: "missing_updates" as const,
      label: "Some information is missing",
      detail:
        alertsWaiting > 0
          ? "We have not received every update yet, and some alerts are waiting to send. Review the items below before using this view for decisions."
          : "We have not received every update yet. Use the dashboard with care until the missing updates arrive.",
      badgeLabel: "Check updates",
      tone: "default" as ReadinessTone,
    };
  }

  if (hasDelayedUpdate) {
    return {
      state: "delayed_updates" as const,
      label: "Updates are delayed",
      detail: "Some parts of the dashboard have not updated on time. Confirm the latest field situation before acting.",
      badgeLabel: "Delayed updates",
      tone: "warning" as ReadinessTone,
    };
  }

  if (alertsWaiting > 0) {
    return {
      state: "needs_attention" as const,
      label: "Needs attention",
      detail: "Some alerts are waiting to send. Review them before treating the dashboard as calm.",
      badgeLabel: "Waiting alerts",
      tone: "warning" as ReadinessTone,
    };
  }

  return {
    state: "ready" as const,
    label: "Ready",
    detail: "Key dashboard updates are current, and alert sending has no waiting items.",
    badgeLabel: "Ready to use",
    tone: "success" as ReadinessTone,
  };
}

type ReadinessEvent = {
  time: string | null;
  label: string;
  message: string;
  tone: "success" | "warning" | "danger" | "default";
};

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
  const hasError = Boolean(systemQuery.error);
  const controlStatus = snapshot?.controlStatus ?? null;

  const riskUpdate = describeUpdate(snapshot?.latestRiskTimestamp ?? null, 360);
  const alertUpdate = describeUpdate(snapshot?.latestAlertTimestamp ?? null, 15);
  const facilityUpdate = describeUpdate(snapshot?.latestFacilityTimestamp ?? null, 1440);
  const chvUpdate = describeUpdate(snapshot?.latestChvTimestamp ?? null, 180);
  const alertsWaiting = (snapshot?.queuedAlerts ?? 0) + (snapshot?.retryPendingAlerts ?? 0);
  const alertDeliveryPaused = controlStatus?.alert_delivery_paused ?? false;
  const controlDisabled = controlAction !== null || !controlStatus;
  const actionStatusTone = controlStatus ? "success" : hasError ? "danger" : "default";
  const actionStatusLabel = controlStatus ? "Actions ready" : hasError ? "Actions unavailable" : "Loading actions";
  const readinessStatus = getReadinessStatus({
    riskUpdate,
    alertUpdate,
    facilityUpdate,
    chvUpdate,
    failedAlerts: snapshot?.failedAlerts ?? 0,
    alertsWaiting,
  });
  const riskNote = getUpdateNote(riskUpdate);
  const alertNote = getUpdateNote(alertUpdate);
  const facilityNote = getUpdateNote(facilityUpdate);
  const chvNote = getUpdateNote(chvUpdate);
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
      const count = result.queued_alert_delivery_count;
      setControlFeedback({
        tone: "success",
        message:
          count > 0
            ? `${formatCountLabel(count, "waiting alert")} ${count === 1 ? "is" : "are"} being sent again.`
            : "No waiting alerts needed another send attempt.",
      });
      await systemQuery.refetch();
    } catch {
      setControlFeedback({
        tone: "danger",
        message: "We could not send waiting alerts again. Try once more or ask the support team to check alert sending.",
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
      await runManualRiskScoringViaBff({
        month,
        trigger_alerts: false,
        send_sms: false,
      });
      setControlFeedback({
        tone: "success",
        message: "Ward risk is being updated. No SMS alerts will be sent from this action.",
      });
      await systemQuery.refetch();
    } catch {
      setControlFeedback({
        tone: "danger",
        message: "We could not start the ward risk update. Try once more or ask the support team to check it.",
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
        reason: nextPausedState ? "Paused from operations readiness page." : "Resumed from operations readiness page.",
      });
      setControlFeedback({
        tone: nextPausedState ? "warning" : "success",
        message: result.alert_delivery_paused
          ? `Outgoing SMS is paused until ${formatDateTimeLabel(result.alert_delivery_paused_until)}.`
          : "Outgoing SMS has resumed.",
      });
      await systemQuery.refetch();
    } catch {
      setControlFeedback({
        tone: "danger",
        message: "We could not change outgoing SMS right now. Try once more or ask the support team to check alert sending.",
      });
    } finally {
      setControlAction(null);
    }
  }

  const summaryCards = useMemo(
    () => [
      {
        title: "Wards shown",
        value: isLoading ? "..." : `${snapshot?.visibleWards ?? 0}`,
        detail: `${snapshot?.wardsWithFreshRisk ?? 0}/${snapshot?.visibleWards ?? 0} have a recent risk update`,
        tone: "info" as const,
        icon: <CloudRain className="size-5" aria-hidden="true" />,
      },
      {
        title: "Wards needing attention",
        value: isLoading ? "..." : `${snapshot?.highRiskWards ?? 0}`,
        detail: riskNote ?? "Based on the latest ward risk update",
        tone:
          riskUpdate.isMissing
            ? ("default" as const)
            : riskUpdate.isDelayed
              ? ("warning" as const)
              : (snapshot?.highRiskWards ?? 0) > 0
                ? ("warning" as const)
                : ("success" as const),
        icon: <Siren className="size-5" aria-hidden="true" />,
      },
      {
        title: "Alerts waiting to send",
        value: isLoading ? "..." : `${alertsWaiting}`,
        detail:
          (snapshot?.failedAlerts ?? 0) > 0
            ? `${formatCountLabel(snapshot?.failedAlerts ?? 0, "alert")} did not send`
            : alertNote ?? `${snapshot?.deliveredAlerts ?? 0} sent recently`,
        tone:
          (snapshot?.failedAlerts ?? 0) > 0
            ? ("danger" as const)
            : alertUpdate.isMissing
              ? ("default" as const)
              : alertUpdate.isDelayed || alertsWaiting > 0
                ? ("warning" as const)
                : ("success" as const),
        icon: <BellRing className="size-5" aria-hidden="true" />,
      },
      {
        title: "CHVs active today",
        value: isLoading ? "..." : `${snapshot?.onlineChvs ?? 0}/${snapshot?.activeChvs ?? 0}`,
        detail: chvNote ?? `${snapshot?.delayedChvs ?? 0} delayed, ${snapshot?.offlineChvs ?? 0} offline right now`,
        tone:
          chvUpdate.isMissing
            ? ("default" as const)
            : chvUpdate.isDelayed || (snapshot?.offlineChvs ?? 0) > 0
              ? ("warning" as const)
              : ("success" as const),
        icon: <ShieldCheck className="size-5" aria-hidden="true" />,
      },
    ],
    [
      alertsWaiting,
      alertNote,
      alertUpdate.isDelayed,
      alertUpdate.isMissing,
      chvNote,
      chvUpdate.isDelayed,
      chvUpdate.isMissing,
      isLoading,
      riskNote,
      riskUpdate.isDelayed,
      riskUpdate.isMissing,
      snapshot?.activeChvs,
      snapshot?.delayedChvs,
      snapshot?.deliveredAlerts,
      snapshot?.failedAlerts,
      snapshot?.highRiskWards,
      snapshot?.offlineChvs,
      snapshot?.onlineChvs,
      snapshot?.visibleWards,
      snapshot?.wardsWithFreshRisk,
    ],
  );

  const updateRows = useMemo(
    () => [
      {
        title: "Ward risk updates",
        evidence: `${snapshot?.wardsWithFreshRisk ?? 0}/${snapshot?.visibleWards ?? 0} wards have a recent risk update`,
        status: riskUpdate.label,
        detail: riskUpdate.detail,
        stateLabel: riskUpdate.stateLabel,
        lastUpdate: snapshot?.latestRiskTimestamp ? `Last update: ${formatRelativeLabel(snapshot.latestRiskTimestamp)}` : "No update received yet",
        tone: riskUpdate.tone,
        icon: <CloudRain className="size-4" aria-hidden="true" />,
      },
      {
        title: "Alert sending",
        evidence: `${snapshot?.visibleAlerts ?? 0} alerts checked; ${alertsWaiting} waiting to send`,
        status:
          (snapshot?.failedAlerts ?? 0) > 0
            ? `${formatCountLabel(snapshot?.failedAlerts ?? 0, "alert")} did not send`
            : alertUpdate.label,
        detail: (snapshot?.failedAlerts ?? 0) > 0 ? "Review now" : alertUpdate.detail,
        stateLabel: (snapshot?.failedAlerts ?? 0) > 0 ? "Needs attention" : alertUpdate.stateLabel,
        lastUpdate: snapshot?.latestAlertTimestamp ? `Last update: ${formatRelativeLabel(snapshot.latestAlertTimestamp)}` : "No update received yet",
        tone: (snapshot?.failedAlerts ?? 0) > 0 ? ("danger" as const) : alertUpdate.tone,
        icon: <BellRing className="size-4" aria-hidden="true" />,
      },
      {
        title: "Facility list",
        evidence: `${snapshot?.visibleFacilities ?? 0} facilities are available in the dashboard`,
        status: facilityUpdate.label,
        detail: facilityUpdate.detail,
        stateLabel: facilityUpdate.stateLabel,
        lastUpdate: snapshot?.latestFacilityTimestamp ? `Last update: ${formatRelativeLabel(snapshot.latestFacilityTimestamp)}` : "No update received yet",
        tone: facilityUpdate.tone,
        icon: <DatabaseZap className="size-4" aria-hidden="true" />,
      },
      {
        title: "CHV activity",
        evidence: `${snapshot?.syncPayloads24h ?? 0} check-ins and ${snapshot?.ussdSessions24h ?? 0} phone menu sessions in the last 24 hours`,
        status: chvUpdate.label,
        detail: chvUpdate.detail,
        stateLabel: chvUpdate.stateLabel,
        lastUpdate: snapshot?.latestChvTimestamp ? `Last update: ${formatRelativeLabel(snapshot.latestChvTimestamp)}` : "No update received yet",
        tone: chvUpdate.tone,
        icon: <Waves className="size-4" aria-hidden="true" />,
      },
    ],
    [
      alertsWaiting,
      alertUpdate.detail,
      alertUpdate.label,
      alertUpdate.stateLabel,
      alertUpdate.tone,
      chvUpdate.detail,
      chvUpdate.label,
      chvUpdate.stateLabel,
      chvUpdate.tone,
      facilityUpdate.detail,
      facilityUpdate.label,
      facilityUpdate.stateLabel,
      facilityUpdate.tone,
      riskUpdate.detail,
      riskUpdate.label,
      riskUpdate.stateLabel,
      riskUpdate.tone,
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

  const activityCards = useMemo(
    () => [
      {
        group: "Alert sending",
        name:
          (snapshot?.visibleAlerts ?? 0) > 0
            ? `${snapshot?.deliveredAlerts ?? 0} sent recently`
            : "No alert activity yet",
        note:
          (snapshot?.failedAlerts ?? 0) > 0
            ? `${formatCountLabel(snapshot?.failedAlerts ?? 0, "alert")} needs review`
            : `${alertsWaiting} waiting to send`,
        tone:
          (snapshot?.failedAlerts ?? 0) > 0
            ? ("danger" as const)
            : alertsWaiting > 0
              ? ("warning" as const)
              : (snapshot?.visibleAlerts ?? 0) > 0
                ? ("success" as const)
                : ("default" as const),
        icon: <BellRing className="size-4" aria-hidden="true" />,
      },
      {
        group: "CHV activity",
        name: `${snapshot?.syncPayloads24h ?? 0} check-ins`,
        note: `${snapshot?.triageSessions24h ?? 0} household checks and ${snapshot?.referrals24h ?? 0} referrals`,
        tone: (snapshot?.syncPayloads24h ?? 0) > 0 ? ("success" as const) : ("default" as const),
        icon: <Waves className="size-4" aria-hidden="true" />,
      },
      {
        group: "Phone menu use",
        name: `${snapshot?.ussdSessions24h ?? 0} sessions`,
        note: "Activity from the last 24 hours",
        tone: (snapshot?.ussdSessions24h ?? 0) > 0 ? ("success" as const) : ("default" as const),
        icon: <BellRing className="size-4" aria-hidden="true" />,
      },
      {
        group: "Facility list",
        name: `${snapshot?.visibleFacilities ?? 0} facilities`,
        note: facilityNote ?? facilityUpdate.detail,
        tone:
          facilityUpdate.tone === "warning"
            ? ("warning" as const)
            : facilityUpdate.tone === "success"
              ? ("success" as const)
              : ("default" as const),
        icon: <DatabaseZap className="size-4" aria-hidden="true" />,
      },
    ],
    [
      alertsWaiting,
      facilityNote,
      facilityUpdate.detail,
      facilityUpdate.tone,
      snapshot?.deliveredAlerts,
      snapshot?.failedAlerts,
      snapshot?.referrals24h,
      snapshot?.syncPayloads24h,
      snapshot?.triageSessions24h,
      snapshot?.ussdSessions24h,
      snapshot?.visibleAlerts,
      snapshot?.visibleFacilities,
    ],
  );

  const readinessEvents: ReadinessEvent[] = useMemo(() => {
    const events: Array<ReadinessEvent | null> = [
      snapshot?.latestRiskTimestamp
        ? {
            time: snapshot.latestRiskTimestamp,
            label: "Updated",
            message: `Ward risk was updated ${formatRelativeLabel(snapshot.latestRiskTimestamp)} for ${snapshot.wardsWithFreshRisk}/${snapshot.visibleWards} wards.`,
            tone: riskUpdate.isDelayed ? ("warning" as const) : ("success" as const),
          }
        : null,
      (snapshot?.failedAlerts ?? 0) > 0
        ? {
            time: snapshot?.latestFailedAlertTimestamp ?? snapshot?.latestAlertTimestamp ?? null,
            label: "Review",
            message: `${formatCountLabel(snapshot?.failedAlerts ?? 0, "alert")} did not send. Review alert sending before relying on this status.`,
            tone: "danger" as const,
          }
        : null,
      (snapshot?.retryPendingAlerts ?? 0) > 0
        ? {
            time: snapshot?.latestRetryAlertTimestamp ?? snapshot?.latestAlertTimestamp ?? null,
            label: "Waiting",
            message: `${formatCountLabel(snapshot?.retryPendingAlerts ?? 0, "alert")} needs another sending attempt.`,
            tone: "warning" as const,
          }
        : null,
      snapshot?.latestChvTimestamp
        ? {
            time: snapshot.latestChvTimestamp,
            label: chvUpdate.isDelayed ? "Delayed" : "Updated",
            message: `CHV activity was updated ${formatRelativeLabel(snapshot.latestChvTimestamp)}.`,
            tone: chvUpdate.isDelayed ? ("warning" as const) : ("success" as const),
          }
        : null,
      snapshot?.latestFacilityTimestamp
        ? {
            time: snapshot.latestFacilityTimestamp,
            label: facilityUpdate.isDelayed ? "Delayed" : "Updated",
            message: `Facility list was updated ${formatRelativeLabel(snapshot.latestFacilityTimestamp)} for ${snapshot.visibleFacilities} facilities.`,
            tone: facilityUpdate.isDelayed ? ("warning" as const) : ("success" as const),
          }
        : null,
      alertsWaiting > 0
        ? {
            time: snapshot?.latestAlertTimestamp ?? null,
            label: "Waiting",
            message: `${formatCountLabel(alertsWaiting, "alert")} waiting to send.`,
            tone: "warning" as const,
          }
        : null,
    ];

    const filteredEvents = events.filter((event): event is ReadinessEvent => event !== null);
    filteredEvents.sort((left, right) => {
      const leftTime = left.time ? new Date(left.time).getTime() : 0;
      const rightTime = right.time ? new Date(right.time).getTime() : 0;
      return rightTime - leftTime;
    });

    return filteredEvents.slice(0, 5);
  }, [
    alertsWaiting,
    chvUpdate.isDelayed,
    facilityUpdate.isDelayed,
    riskUpdate.isDelayed,
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
        title="Operations Readiness"
        subtitle="Check whether dashboard information is current and safe to use."
        lastUpdatedLabel={lastUpdatedLabel}
        lastUpdatedTone={
          readinessStatus.state !== "ready" &&
          (riskUpdate.isDelayed || alertUpdate.isDelayed || facilityUpdate.isDelayed || chvUpdate.isDelayed)
            ? "stale"
            : "default"
        }
        onRefresh={() => {
          void systemQuery.refetch();
        }}
      />

      <RoleGate
        pageCapability="system"
        title="You need permission to view this page"
        message="Admins and analysts can review readiness and safe actions."
      >
        {hasError ? (
          <StatusBanner tone="danger" icon={<AlertTriangle aria-hidden="true" />}>
            We could not load readiness information right now. Refresh the page or try again shortly.
          </StatusBanner>
        ) : null}

        <Card
          className={cn(
            "rounded-[2rem] px-5 py-5 sm:px-6",
            readinessStatus.tone === "success" &&
              "border-[color-mix(in_srgb,var(--success)_24%,transparent)] bg-[color-mix(in_srgb,var(--success)_7%,var(--panel))]",
            readinessStatus.tone === "warning" &&
              "border-[color-mix(in_srgb,var(--warning)_28%,transparent)] bg-[color-mix(in_srgb,var(--warning)_8%,var(--panel))]",
            readinessStatus.tone === "danger" &&
              "border-[color-mix(in_srgb,var(--danger)_28%,transparent)] bg-[color-mix(in_srgb,var(--danger)_8%,var(--panel))]",
            readinessStatus.tone === "default" &&
              "border-[color-mix(in_srgb,var(--dashboard-subtle-copy)_24%,transparent)] bg-[color-mix(in_srgb,var(--dashboard-subtle-copy)_7%,var(--panel))]",
          )}
        >
          <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
            <div className="flex items-start gap-4">
              <span
                className={cn(
                  "inline-flex size-11 shrink-0 items-center justify-center rounded-2xl",
                  readinessStatus.tone === "success" &&
                    "bg-[color-mix(in_srgb,var(--success)_16%,transparent)] text-[color:var(--success)]",
                  readinessStatus.tone === "warning" &&
                    "bg-[color-mix(in_srgb,var(--warning)_16%,transparent)] text-[color:var(--warning)]",
                  readinessStatus.tone === "danger" &&
                    "bg-[color-mix(in_srgb,var(--danger)_16%,transparent)] text-[color:var(--danger)]",
                  readinessStatus.tone === "default" &&
                    "bg-[color-mix(in_srgb,var(--dashboard-subtle-copy)_15%,transparent)] text-panel-muted",
                )}
              >
                {readinessStatus.tone === "success" ? (
                  <ShieldCheck className="size-5" aria-hidden="true" />
                ) : readinessStatus.tone === "danger" ? (
                  <AlertTriangle className="size-5" aria-hidden="true" />
                ) : readinessStatus.tone === "warning" ? (
                  <Clock3 className="size-5" aria-hidden="true" />
                ) : (
                  <DatabaseZap className="size-5" aria-hidden="true" />
                )}
              </span>
              <div>
                <p className="text-xs font-semibold text-panel-subtle">Readiness check</p>
                <h2 className="mt-2 text-2xl font-semibold text-panel-strong">
                  {isLoading ? "Checking readiness" : readinessStatus.label}
                </h2>
                <p className="mt-2 max-w-3xl text-sm leading-6 text-panel-muted">
                  {isLoading ? "Checking the latest dashboard updates before giving guidance." : readinessStatus.detail}
                </p>
              </div>
            </div>
            <StatusBadge
              tone={
                readinessStatus.tone === "danger"
                  ? "danger"
                  : readinessStatus.tone === "warning"
                    ? "warning"
                    : readinessStatus.tone === "success"
                      ? "success"
                      : "default"
              }
              className="w-fit px-3 py-1 normal-case tracking-normal"
            >
              {readinessStatus.badgeLabel}
            </StatusBadge>
          </div>
        </Card>

        <section className="grid gap-4 xl:grid-cols-4">
          {summaryCards.map((card) => (
            <Card key={card.title} className="rounded-[1.5rem] px-5 py-5">
              <div className="flex items-start justify-between gap-4">
                <div className="space-y-3">
                  <p className="text-sm font-semibold text-panel-muted">{card.title}</p>
                  <div className="space-y-1">
                    <div className="text-[2rem] font-semibold leading-none text-panel-strong">
                      {card.value}
                    </div>
                    <p className="text-sm leading-6 text-panel-muted">{card.detail}</p>
                  </div>
                </div>
                <span
                  className={cn(
                    "inline-flex size-11 shrink-0 items-center justify-center rounded-2xl border",
                    toneIconSurfaceClasses(card.tone),
                  )}
                >
                  {card.icon}
                </span>
              </div>
            </Card>
          ))}
        </section>

        <section>
          <Card className="rounded-[2rem] px-5 py-5 sm:px-6">
            <PageSectionHeader
              className="gap-1"
              title="Are updates current?"
              description="Use this check to see which areas are current and which ones need a closer look."
              actions={
                <Button
                  variant="secondary"
                  className="h-10 rounded-pill px-4"
                  onClick={() => {
                    void systemQuery.refetch();
                  }}
                >
                  <RefreshCcw className="mr-2 size-4" aria-hidden="true" />
                  Refresh status
                </Button>
              }
            />

            <div className="mt-5 space-y-3">
              {updateRows.map((row) => (
                <div
                  key={row.title}
                  className={cn(
                    "flex flex-col gap-3 rounded-[1.25rem] border px-4 py-4 sm:flex-row sm:items-center sm:justify-between",
                    readinessRowSurfaceClasses(row.tone),
                  )}
                >
                  <div className="flex items-start gap-3">
                    <span
                      className={cn(
                        "inline-flex size-10 shrink-0 items-center justify-center rounded-2xl border",
                        toneIconSurfaceClasses(row.tone),
                      )}
                    >
                      {row.icon}
                    </span>
                    <div>
                      <strong className="block text-sm font-semibold text-panel-strong">{row.title}</strong>
                      <p className="mt-1 text-xs leading-5 text-panel-muted">{row.evidence}</p>
                      <p className="mt-1 text-xs font-medium text-panel-subtle">{row.lastUpdate}</p>
                    </div>
                  </div>

                  <div className="space-y-1 sm:text-right">
                    <div className="text-sm font-semibold text-panel-strong">{row.status}</div>
                    <StatusBadge
                      tone={row.tone === "danger" ? "danger" : row.tone === "warning" ? "warning" : row.tone === "success" ? "success" : "default"}
                      className="px-2.5 py-1 normal-case tracking-normal"
                    >
                      {row.stateLabel}
                    </StatusBadge>
                    <div className="text-xs font-medium text-panel-muted">{row.detail}</div>
                  </div>
                </div>
              ))}
            </div>
          </Card>
        </section>

        <section>
          <Card className="rounded-[2rem] px-5 py-5 sm:px-6">
            <PageSectionHeader
              className="gap-1"
              title="Recent activity"
              description="A short view of alert sending, CHV activity, phone menu use, and the facility list."
            />

            <div className="mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
              {activityCards.map((activity) => (
                <div key={`${activity.group}-${activity.name}`} className="rounded-[1.25rem] border border-panel-table-wrap px-3.5 py-3.5">
                  <div className="flex items-start justify-between gap-3">
                    <span
                      className={cn(
                        "inline-flex size-8 items-center justify-center rounded-xl border",
                        toneIconSurfaceClasses(activity.tone),
                      )}
                    >
                      {activity.icon}
                    </span>
                    <span
                      className={cn(
                        "mt-1 size-2 rounded-full",
                        activity.tone === "success" && "bg-[color:var(--success)]",
                        activity.tone === "warning" && "bg-[color:var(--warning)]",
                        activity.tone === "danger" && "bg-[color:var(--danger)]",
                        activity.tone === "default" && "bg-[var(--dashboard-subtle-copy)]",
                      )}
                    />
                  </div>
                  <p className="mt-3 text-xs font-semibold text-panel-subtle">{activity.group}</p>
                  <strong className="mt-1 block text-sm font-semibold text-panel-strong">{activity.name}</strong>
                  <p
                    className={cn(
                      "mt-2 text-xs font-medium",
                      activity.tone === "success" && "text-[color:var(--success)]",
                      activity.tone === "warning" && "text-[color:var(--warning)]",
                      activity.tone === "danger" && "text-[color:var(--danger)]",
                      activity.tone === "default" && "text-panel-muted",
                    )}
                  >
                    {activity.note}
                  </p>
                </div>
              ))}
            </div>

            <div className="mt-6">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="text-sm font-semibold text-panel-strong">Activity log</p>
                  <p className="mt-1 text-xs text-panel-muted">These notes help you spot what changed recently.</p>
                </div>
                <span className="inline-flex items-center gap-2 text-xs font-medium text-panel-muted">
                  <Logs className="size-4" aria-hidden="true" />
                  {readinessEvents.length > 0 ? `${readinessEvents.length} recent notes` : "No recent notes"}
                </span>
              </div>

              <div className="mt-3 overflow-hidden rounded-[1.25rem] border border-panel-table-wrap">
                <div className="divide-y divide-[var(--dashboard-table-line)]">
                  {readinessEvents.length > 0 ? (
                    readinessEvents.map((event, index) => (
                      <div key={`${event.label}-${index}`} className="grid gap-3 px-4 py-3 md:grid-cols-[4.5rem_6rem_minmax(0,1fr)] md:items-center">
                        <div className="text-xs font-medium text-panel-muted">{formatEventTime(event.time)}</div>
                        <StatusBadge
                          tone={event.tone === "danger" ? "danger" : event.tone === "warning" ? "warning" : event.tone === "success" ? "success" : "default"}
                          className="w-fit px-2.5 py-1 normal-case tracking-normal"
                        >
                          {event.label}
                        </StatusBadge>
                        <div className="text-sm leading-6 text-panel-copy">{event.message}</div>
                      </div>
                    ))
                  ) : (
                    <div className="px-4 py-6 text-sm text-panel-muted">Recent activity will appear after updates arrive.</div>
                  )}
                </div>
              </div>
            </div>
          </Card>
        </section>

        <section>
          <Card className="rounded-[2rem] px-5 py-5 sm:px-6">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
              <PageSectionHeader
                className="gap-1"
                title="Safe actions"
                description="Use these only when the readiness check says something needs attention."
              />
              <StatusBadge tone={actionStatusTone} className="w-fit px-3 py-1 normal-case tracking-normal">
                {actionStatusLabel}
              </StatusBadge>
            </div>

            {!controlStatus && hasError ? (
              <StatusBanner tone="danger" className="mt-5" icon={<AlertTriangle aria-hidden="true" />}>
                Safe actions could not load right now.
              </StatusBanner>
            ) : null}

            {controlFeedback ? (
              <StatusBanner tone={controlFeedback.tone} className="mt-5">
                {controlFeedback.message}
              </StatusBanner>
            ) : null}

            {alertDeliveryPaused ? (
              <StatusBanner tone="warning" className="mt-5" icon={<ShieldAlert aria-hidden="true" />}>
                Outgoing SMS is paused until {formatDateTimeLabel(controlStatus?.alert_delivery_paused_until ?? null)}.
              </StatusBanner>
            ) : null}

            <div className="mt-5 grid gap-4 xl:grid-cols-3">
              <div className="rounded-[1.35rem] border border-panel-table-wrap px-4 py-4">
                <div className="flex items-center gap-3">
                  <span className={cn("inline-flex size-9 items-center justify-center rounded-xl border", toneIconSurfaceClasses("success"))}>
                    <RefreshCcw className="size-4" aria-hidden="true" />
                  </span>
                  <h3 className="text-sm font-semibold text-panel-strong">Try sending waiting alerts again</h3>
                </div>
                <p className="mt-4 text-sm leading-6 text-panel-muted">
                  Use this when alerts are waiting or need another sending attempt.
                </p>
                <p className="mt-3 text-xs font-semibold text-panel-subtle">
                  Waiting now: {alertsWaiting}
                </p>
                <Button
                  variant="secondary"
                  size="sm"
                  className="mt-4"
                  onClick={handleRetryBackgroundJobs}
                  disabled={controlDisabled || !controlStatus?.can_retry_background_jobs}
                >
                  <RefreshCcw className={cn("size-4", controlAction === "retry" && "animate-spin")} aria-hidden="true" />
                  Send waiting alerts
                </Button>
              </div>

              <div className="rounded-[1.35rem] border border-panel-table-wrap px-4 py-4">
                <div className="flex items-center gap-3">
                  <span className={cn("inline-flex size-9 items-center justify-center rounded-xl border", toneIconSurfaceClasses("info"))}>
                    <Siren className="size-4" aria-hidden="true" />
                  </span>
                  <h3 className="text-sm font-semibold text-panel-strong">Update ward risk now</h3>
                </div>
                <p className="mt-4 text-sm leading-6 text-panel-muted">
                  Refresh ward risk for the current month. This action does not send SMS alerts.
                </p>
                <p className="mt-3 text-xs font-semibold text-panel-subtle">
                  No SMS will be sent
                </p>
                <Button
                  variant="secondary"
                  size="sm"
                  className="mt-4"
                  onClick={handleManualRiskScoring}
                  disabled={controlDisabled || !controlStatus?.can_run_manual_risk_scoring}
                >
                  <Siren className="size-4" aria-hidden="true" />
                  Update ward risk
                </Button>
              </div>

              <div className="rounded-[1.35rem] border border-panel-table-wrap px-4 py-4">
                <div className="flex items-center gap-3">
                  <span
                    className={cn(
                      "inline-flex size-9 items-center justify-center rounded-xl border",
                      toneIconSurfaceClasses(alertDeliveryPaused ? "warning" : "success"),
                    )}
                  >
                    <BellRing className="size-4" aria-hidden="true" />
                  </span>
                  <h3 className="text-sm font-semibold text-panel-strong">Outgoing SMS</h3>
                </div>
                <p className="mt-4 text-sm leading-6 text-panel-muted">
                  {alertDeliveryPaused
                    ? "Resume messages when the team is ready for alerts to go out again."
                    : "Pause new SMS while staff verify information. Dashboard alerts stay visible."}
                </p>
                <p className="mt-3 text-xs font-semibold text-panel-subtle">
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
                  {alertDeliveryPaused ? "Resume outgoing SMS" : "Pause outgoing SMS"}
                </Button>
              </div>
            </div>
          </Card>
        </section>
      </RoleGate>
    </div>
  );
}
