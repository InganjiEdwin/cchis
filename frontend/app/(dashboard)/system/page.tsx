"use client";

import {
  AlertTriangle,
  BellRing,
  Clock3,
  CloudRain,
  DatabaseZap,
  Gauge,
  Logs,
  PauseCircle,
  PlayCircle,
  RefreshCcw,
  RotateCcw,
  ServerCog,
  ShieldAlert,
  ShieldCheck,
  Siren,
  Waves,
  Waypoints,
} from "lucide-react";
import { useMemo } from "react";

import { useAuth } from "@/components/auth-provider";
import { DashboardTopbar } from "@/components/dashboard-topbar";
import { RoleGate } from "@/components/role-gate";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { PageSectionHeader } from "@/components/ui/page-section-header";
import { StatusBanner } from "@/components/ui/status-banner";
import { StatusBadge } from "@/components/ui/status-badge";
import { cn } from "@/lib/cn";
import { useSystemQuery } from "@/queries/use-system-query";

function formatRelativeLabel(timestamp: string | null) {
  if (!timestamp) {
    return "No recent update";
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

function describeFreshness(timestamp: string | null, thresholdMinutes: number) {
  if (!timestamp) {
    return {
      label: "No visible timestamp available",
      detail: "Awaiting visible records",
      isStale: true,
      tone: "danger" as const,
    };
  }

  const ageMinutes = Math.max(0, Math.round((Date.now() - new Date(timestamp).getTime()) / 60000));

  if (ageMinutes > thresholdMinutes * 2) {
    return {
      label: `${formatRelativeLabel(timestamp)} update`,
      detail: "Older visible data",
      isStale: true,
      tone: "danger" as const,
    };
  }

  if (ageMinutes > thresholdMinutes) {
    return {
      label: `${formatRelativeLabel(timestamp)} update`,
      detail: "Older than target window",
      isStale: true,
      tone: "warning" as const,
    };
  }

  return {
    label: `${formatRelativeLabel(timestamp)} update`,
    detail: "Within target window",
    isStale: false,
    tone: "success" as const,
  };
}

function toPipelineState(tone: "success" | "warning" | "danger" | "default") {
  if (tone === "success") {
    return "Within window";
  }
  if (tone === "warning") {
    return "Review";
  }
  if (tone === "danger") {
    return "Outside window";
  }
  return "Pending";
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

export default function SystemPage() {
  const { currentUser } = useAuth();
  const systemQuery = useSystemQuery({ enabled: Boolean(currentUser) });
  const snapshot = systemQuery.data ?? null;
  const isLoading = systemQuery.isPending;
  const isRefreshing = systemQuery.isFetching;
  const error = systemQuery.error instanceof Error ? systemQuery.error.message : null;

  const riskFreshness = describeFreshness(snapshot?.latestRiskTimestamp ?? null, 360);
  const alertFreshness = describeFreshness(snapshot?.latestAlertTimestamp ?? null, 15);
  const facilityFreshness = describeFreshness(snapshot?.latestFacilityTimestamp ?? null, 1440);
  const chvFreshness = describeFreshness(snapshot?.latestChvTimestamp ?? null, 180);
  const lastUpdatedLabel = isRefreshing
    ? "Refreshing..."
    : formatRelativeLabel(
        snapshot?.latestAlertTimestamp ??
          snapshot?.latestChvTimestamp ??
          snapshot?.latestRiskTimestamp ??
          snapshot?.latestFacilityTimestamp ??
          null,
      );

  const alertBacklog = (snapshot?.queuedAlerts ?? 0) + (snapshot?.retryPendingAlerts ?? 0);
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
        detail: "From visible ward risk classifications",
        tone: (snapshot?.highRiskWards ?? 0) > 0 ? ("warning" as const) : ("success" as const),
        icon: <Siren className="size-5" aria-hidden="true" />,
      },
      {
        title: "Alert Backlog",
        value: isLoading ? "..." : `${alertBacklog}`,
        detail: `${snapshot?.failedAlerts ?? 0} failed deliveries in visible records`,
        tone: (snapshot?.failedAlerts ?? 0) > 0 ? ("danger" as const) : alertBacklog > 0 ? ("warning" as const) : ("success" as const),
        icon: <BellRing className="size-5" aria-hidden="true" />,
      },
      {
        title: "CHV Sync Summary",
        value: isLoading ? "..." : `${snapshot?.onlineChvs ?? 0}/${snapshot?.activeChvs ?? 0}`,
        detail: `${snapshot?.delayedChvs ?? 0} delayed, ${snapshot?.offlineChvs ?? 0} offline in visible CHV records`,
        tone: (snapshot?.offlineChvs ?? 0) > 0 ? ("warning" as const) : ("success" as const),
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
    ],
  );

  const freshnessFeeds = useMemo(
    () => [
      {
        title: "Risk Scoring Feed",
        subtitle: `${snapshot?.wardsWithFreshRisk ?? 0}/${snapshot?.visibleWards ?? 0} wards expose generated risk timestamps`,
        status: riskFreshness.label,
        detail: riskFreshness.detail,
        tone: riskFreshness.tone,
        icon: <CloudRain className="size-4" aria-hidden="true" />,
      },
      {
        title: "Alert Delivery Feed",
        subtitle: `${snapshot?.visibleAlerts ?? 0} alerts visible, ${alertBacklog} queued or retry-pending`,
        status: alertFreshness.label,
        detail: alertFreshness.detail,
        tone: alertFreshness.tone,
        icon: <BellRing className="size-4" aria-hidden="true" />,
      },
      {
        title: "Facility Registry",
        subtitle: `${snapshot?.visibleFacilities ?? 0} facility records are visible`,
        status: facilityFreshness.label,
        detail: facilityFreshness.detail,
        tone: facilityFreshness.tone,
        icon: <DatabaseZap className="size-4" aria-hidden="true" />,
      },
      {
        title: "CHV Operations Feed",
        subtitle: `${snapshot?.syncPayloads24h ?? 0} sync payloads, ${snapshot?.ussdSessions24h ?? 0} USSD sessions in the last 24h`,
        status: chvFreshness.label,
        detail: chvFreshness.detail,
        tone: chvFreshness.tone,
        icon: <Waves className="size-4" aria-hidden="true" />,
      },
    ],
    [
      alertBacklog,
      alertFreshness.detail,
      alertFreshness.label,
      alertFreshness.tone,
      chvFreshness.detail,
      chvFreshness.label,
      chvFreshness.tone,
      facilityFreshness.detail,
      facilityFreshness.label,
      facilityFreshness.tone,
      riskFreshness.detail,
      riskFreshness.label,
      riskFreshness.tone,
      snapshot?.syncPayloads24h,
      snapshot?.ussdSessions24h,
      snapshot?.visibleAlerts,
      snapshot?.visibleFacilities,
      snapshot?.visibleWards,
      snapshot?.wardsWithFreshRisk,
    ],
  );

  const pipelines = useMemo(
    () => [
      {
        name: "Risk Scoring Coverage",
        state:
          snapshot && snapshot.visibleWards > 0
            ? `${snapshot.wardsWithFreshRisk}/${snapshot.visibleWards} wards have recent model records`
            : "Awaiting ward risk records",
        tone:
          !snapshot || snapshot.visibleWards === 0
            ? ("default" as const)
            : snapshot.wardsWithFreshRisk === snapshot.visibleWards && !riskFreshness.isStale
              ? ("success" as const)
              : riskFreshness.isStale
                ? ("warning" as const)
                : ("default" as const),
      },
      {
        name: "Alert Delivery Queue",
        state: `${snapshot?.queuedAlerts ?? 0} queued, ${snapshot?.retryPendingAlerts ?? 0} retrying, ${snapshot?.failedAlerts ?? 0} failed`,
        tone:
          (snapshot?.failedAlerts ?? 0) > 0
            ? ("danger" as const)
            : alertBacklog > 0
              ? ("warning" as const)
              : ("success" as const),
      },
      {
        name: "CHV Sync Ingest",
        state: `${snapshot?.onlineChvs ?? 0} online, ${snapshot?.delayedChvs ?? 0} delayed, ${snapshot?.offlineChvs ?? 0} offline`,
        tone:
          (snapshot?.offlineChvs ?? 0) > 0
            ? ("warning" as const)
            : (snapshot?.onlineChvs ?? 0) > 0
              ? ("success" as const)
              : ("default" as const),
      },
      {
        name: "Facility Registry Freshness",
        state: facilityFreshness.label,
        tone:
          facilityFreshness.tone === "danger"
            ? ("danger" as const)
            : facilityFreshness.tone === "warning"
              ? ("warning" as const)
              : ("success" as const),
      },
    ],
    [
      alertBacklog,
      alertFreshness.isStale,
      facilityFreshness.label,
      facilityFreshness.tone,
      riskFreshness.isStale,
      snapshot,
    ],
  );

  const observedChannels = useMemo(
    () => [
      {
        group: "Alert delivery backends",
        name:
          snapshot?.deliveryBackends.length
            ? snapshot.deliveryBackends
                .slice(0, 2)
                .map((item) => item.name)
                .join(", ")
            : "No recent alert backend observed",
        note: snapshot?.deliveryBackends.length
          ? `${snapshot.deliveryBackends.reduce((sum, item) => sum + item.count, 0)} recent alerts sampled through delivery metadata`
          : "Awaiting recent alert activity",
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
        note: "Derived from backend USSD session logs",
        tone: (snapshot?.ussdSessions24h ?? 0) > 0 ? ("success" as const) : ("default" as const),
        icon: <BellRing className="size-4" aria-hidden="true" />,
      },
      {
        group: "Facility registry",
        name: `${snapshot?.visibleFacilities ?? 0} facility records`,
        note: facilityFreshness.detail,
        tone:
          facilityFreshness.tone === "danger"
            ? ("danger" as const)
            : facilityFreshness.tone === "warning"
              ? ("warning" as const)
              : ("success" as const),
        icon: <DatabaseZap className="size-4" aria-hidden="true" />,
      },
    ],
    [
      facilityFreshness.detail,
      facilityFreshness.tone,
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
        title="System Summary"
        subtitle="Read-only system summary derived from dashboard records"
        lastUpdatedLabel={lastUpdatedLabel}
        lastUpdatedTone={
          riskFreshness.isStale || alertFreshness.isStale || facilityFreshness.isStale || chvFreshness.isStale
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
        message="Only Admin and Analyst roles should access this read-only system summary page."
      >
        {error ? (
          <StatusBanner tone="danger" icon={<AlertTriangle aria-hidden="true" />}>
            {error}
          </StatusBanner>
        ) : null}

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

        <section className="grid gap-6 xl:grid-cols-[minmax(0,1.55fr)_20rem]">
          <Card className="rounded-[2rem] px-5 py-5 sm:px-6">
            <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
              <PageSectionHeader
                className="gap-1"
                title="Data Freshness"
                description="These signals are derived from backend timestamps, not infrastructure probe data."
              />
              <Button
                variant="secondary"
                className="h-10 rounded-pill px-4"
                onClick={() => {
                  void systemQuery.refetch();
                }}
              >
                <RefreshCcw className="mr-2 size-4" aria-hidden="true" />
                Refresh view
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
                      "border-[color-mix(in_srgb,var(--danger)_18%,white)] bg-[color-mix(in_srgb,var(--danger)_8%,white)] dark:border-[color-mix(in_srgb,var(--danger)_26%,transparent)] dark:bg-[color-mix(in_srgb,var(--danger)_12%,transparent)]",
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
                      )}
                    >
                      {feed.icon}
                    </span>
                    <div>
                      <strong className="block text-sm font-semibold text-panel-strong">{feed.title}</strong>
                      <p className="mt-1 text-xs text-panel-muted">{feed.subtitle}</p>
                    </div>
                  </div>

                  <div className="space-y-1 text-right">
                    <div className="text-sm font-semibold text-panel-strong">{feed.status}</div>
                    <div
                      className={cn(
                        "text-[0.68rem] font-semibold uppercase tracking-[0.14em]",
                        feed.tone === "success" && "text-[color:var(--success)]",
                        feed.tone === "warning" && "text-[color:var(--warning)]",
                        feed.tone === "danger" && "text-[color:var(--danger)]",
                      )}
                    >
                      {feed.detail}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </Card>

          <Card className="rounded-[2rem] border-none bg-[linear-gradient(180deg,#165fbe_0%,#0f56b0_100%)] px-5 py-5 text-white shadow-[0_20px_40px_rgba(15,86,176,0.28)]">
            <div className="flex items-center gap-3">
              <span className="inline-flex size-11 items-center justify-center rounded-2xl bg-white/12 text-white">
                <ServerCog className="size-5" aria-hidden="true" />
              </span>
              <div>
                <h2 className="text-xl font-semibold tracking-[-0.03em]">Unavailable Controls</h2>
                <p className="mt-1 text-sm text-white/74">These controls remain unavailable until backend job-control routes exist.</p>
              </div>
            </div>

            <div className="mt-5 space-y-3">
              {[
                { label: "Retry jobs unavailable", icon: <RotateCcw className="size-4" aria-hidden="true" /> },
                { label: "Manual risk scoring unavailable", icon: <Gauge className="size-4" aria-hidden="true" /> },
                { label: "Alert pause unavailable", icon: <PauseCircle className="size-4" aria-hidden="true" /> },
              ].map((action) => (
                <button
                  key={action.label}
                  type="button"
                  disabled
                  className="flex w-full cursor-not-allowed items-center justify-between rounded-[1.25rem] border border-white/12 bg-white/10 px-4 py-3 text-left opacity-70"
                >
                  <span className="flex items-center gap-3">
                    <span className="inline-flex size-9 items-center justify-center rounded-xl bg-white/10">
                      {action.icon}
                    </span>
                    <span className="text-sm font-semibold">{action.label}</span>
                  </span>
                  <PlayCircle className="size-4 text-white/80" aria-hidden="true" />
                </button>
              ))}
            </div>

            <div className="mt-5 rounded-[1.25rem] border border-white/10 bg-black/10 px-4 py-4">
              <p className="text-[0.68rem] font-semibold uppercase tracking-[0.18em] text-white/60">Limitation</p>
              <p className="mt-2 text-sm font-semibold">Read-only system page</p>
              <p className="mt-1 text-xs text-white/64">
                This page shows system summaries from backend records only. Manual control actions remain unavailable until owned by real APIs.
              </p>
            </div>
          </Card>
        </section>

        <section className="grid gap-6 xl:grid-cols-2">
          <Card className="rounded-[2rem] px-5 py-5 sm:px-6">
            <PageSectionHeader
              className="gap-1"
              title="Pipeline Summary"
              description="Status derived from visible records, not scheduler telemetry."
            />

            <div className="mt-5 space-y-3">
              {pipelines.map((pipeline) => (
                <div key={pipeline.name} className="flex items-center justify-between gap-4 rounded-[1.2rem] px-1 py-1">
                  <div className="flex items-center gap-3">
                    <span
                      className={cn(
                        "size-2.5 rounded-full",
                        pipeline.tone === "success" && "bg-[color:var(--success)]",
                        pipeline.tone === "warning" && "bg-[color:var(--warning)]",
                        pipeline.tone === "danger" && "bg-[color:var(--danger)]",
                        pipeline.tone === "default" && "bg-[var(--dashboard-subtle-copy)]",
                      )}
                    />
                    <span className="text-sm font-medium text-panel-copy">{pipeline.name}</span>
                  </div>
                  <StatusBadge
                    tone={
                      pipeline.tone === "danger"
                        ? "danger"
                        : pipeline.tone === "warning"
                          ? "warning"
                          : pipeline.tone === "success"
                            ? "success"
                            : "default"
                    }
                    className="px-3 py-1 tracking-[0.14em]"
                  >
                    {toPipelineState(pipeline.tone)}
                  </StatusBadge>
                </div>
              ))}
            </div>
          </Card>

          <Card className="rounded-[2rem] px-5 py-5 sm:px-6">
            <PageSectionHeader
              className="gap-1"
              title="Observed Channels"
              description="Activity is surfaced only where a backend source already exists."
            />

            <div className="mt-5 grid gap-3 sm:grid-cols-2">
              {observedChannels.map((integration) => (
                <div key={`${integration.group}-${integration.name}`} className="rounded-[1.35rem] border border-panel-table-wrap px-4 py-4">
                  <div className="flex items-start justify-between gap-3">
                    <span
                      className={cn(
                        "inline-flex size-9 items-center justify-center rounded-xl",
                        integration.tone === "success" &&
                          "bg-[color-mix(in_srgb,var(--success)_14%,white)] text-[color:var(--success)] dark:bg-[color-mix(in_srgb,var(--success)_20%,transparent)]",
                        integration.tone === "warning" &&
                          "bg-[color-mix(in_srgb,var(--warning)_14%,white)] text-[color:var(--warning)] dark:bg-[color-mix(in_srgb,var(--warning)_20%,transparent)]",
                        integration.tone === "danger" &&
                          "bg-[color-mix(in_srgb,var(--danger)_14%,white)] text-[color:var(--danger)] dark:bg-[color-mix(in_srgb,var(--danger)_20%,transparent)]",
                        integration.tone === "default" &&
                          "bg-[color-mix(in_srgb,var(--dashboard-subtle-copy)_16%,white)] text-panel-muted",
                      )}
                    >
                      {integration.icon}
                    </span>
                    <span
                      className={cn(
                        "mt-1 size-2 rounded-full",
                        integration.tone === "success" && "bg-[color:var(--success)]",
                        integration.tone === "warning" && "bg-[color:var(--warning)]",
                        integration.tone === "danger" && "bg-[color:var(--danger)]",
                        integration.tone === "default" && "bg-[var(--dashboard-subtle-copy)]",
                      )}
                    />
                  </div>
                  <p className="mt-4 text-[0.68rem] font-semibold uppercase tracking-[0.18em] text-panel-subtle">
                    {integration.group}
                  </p>
                  <strong className="mt-1 block text-sm font-semibold text-panel-strong">{integration.name}</strong>
                  <p
                    className={cn(
                      "mt-2 text-xs font-medium",
                      integration.tone === "success" && "text-[color:var(--success)]",
                      integration.tone === "warning" && "text-[color:var(--warning)]",
                      integration.tone === "danger" && "text-[color:var(--danger)]",
                      integration.tone === "default" && "text-panel-muted",
                    )}
                  >
                    {integration.note}
                  </p>
                </div>
              ))}
            </div>
          </Card>
        </section>

        <Card className="rounded-[2rem] px-5 py-5 sm:px-6">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
            <PageSectionHeader
              className="gap-1"
              title="Observed Record Stream"
              description="This is a derived record summary, not a raw infrastructure log sink."
            />
            <div className="flex flex-wrap items-center gap-2">
              <StatusBadge tone="default" className="px-3 py-1 tracking-[0.14em]">
                Read-only
              </StatusBadge>
              <StatusBadge tone="default" className="px-3 py-1 tracking-[0.14em]">
                Record-derived
              </StatusBadge>
            </div>
          </div>

          <div className="mt-5 overflow-hidden rounded-[1.4rem] border border-panel-table-wrap">
            <div className="divide-y divide-[var(--dashboard-table-line)]">
              {systemEvents.length > 0 ? (
                systemEvents.map((event, index) => (
                  <div key={`${event.level}-${index}`} className="grid gap-3 px-4 py-3 md:grid-cols-[5.5rem_5.5rem_minmax(0,1fr)] md:items-center">
                    <div className="text-xs font-medium text-panel-muted">{formatEventTime(event.time)}</div>
                    <div className="flex items-center gap-2">
                      <span
                        className={cn(
                          "h-8 w-1 rounded-full",
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
                <div className="px-4 py-6 text-sm text-panel-muted">No events are available for this view yet.</div>
              )}
            </div>
          </div>

          <div className="mt-5 flex flex-wrap items-center gap-4 text-sm text-panel-muted">
            <span className="inline-flex items-center gap-2">
              <Logs className="size-4" aria-hidden="true" />
              Event summaries come from dashboard records.
            </span>
            <span className="inline-flex items-center gap-2">
              <Clock3 className="size-4" aria-hidden="true" />
              Alert freshness: {alertFreshness.detail}
            </span>
            <span className="inline-flex items-center gap-2">
              <ShieldAlert className="size-4" aria-hidden="true" />
              Unsupported infra probes remain unavailable until backend contracts exist.
            </span>
          </div>
        </Card>
      </RoleGate>
    </div>
  );
}
