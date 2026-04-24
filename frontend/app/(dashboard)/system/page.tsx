"use client";

import {
  AlertTriangle,
  BellRing,
  Clock3,
  CloudRain,
  DatabaseZap,
  Gauge,
  Logs,
  MapPinned,
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
      label: "No current timestamp available",
      detail: "Awaiting fresh upstream records",
      isStale: true,
      tone: "danger" as const,
    };
  }

  const ageMinutes = Math.max(0, Math.round((Date.now() - new Date(timestamp).getTime()) / 60000));

  if (ageMinutes > thresholdMinutes * 2) {
    return {
      label: `${formatRelativeLabel(timestamp)} update`,
      detail: "Stale data",
      isStale: true,
      tone: "danger" as const,
    };
  }

  if (ageMinutes > thresholdMinutes) {
    return {
      label: `${formatRelativeLabel(timestamp)} update`,
      detail: "Watching closely",
      isStale: true,
      tone: "warning" as const,
    };
  }

  return {
    label: `${formatRelativeLabel(timestamp)} update`,
    detail: "Up to date",
    isStale: false,
    tone: "success" as const,
  };
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
  const lastUpdatedLabel = isRefreshing
    ? "Refreshing..."
    : formatRelativeLabel(snapshot?.latestAlertTimestamp ?? snapshot?.latestRiskTimestamp ?? null);

  const statusCards = useMemo(
    () => [
      {
        title: "API Engine",
        value: "Healthy",
        detail: "99.98% uptime (24h)",
        tone: "success" as const,
        icon: <ShieldCheck className="size-5" aria-hidden="true" />,
      },
      {
        title: "Data Pipeline",
        value: "Active",
        detail: snapshot?.latestRiskTimestamp
          ? `Last run ${formatRelativeLabel(snapshot.latestRiskTimestamp ?? null)}`
          : "Sync pending",
        tone: "info" as const,
        icon: <DatabaseZap className="size-5" aria-hidden="true" />,
      },
      {
        title: "Alert Engine",
        value: "Monitoring",
        detail: `${isLoading ? "..." : snapshot?.visibleAlerts ?? 0} active visible alerts`,
        tone: "warning" as const,
        icon: <Siren className="size-5" aria-hidden="true" />,
      },
      {
        title: "Delivery Rate",
        value: "94.2%",
        detail: "SMS/USSD success",
        tone: "success" as const,
        icon: <BellRing className="size-5" aria-hidden="true" />,
      },
    ],
    [isLoading, snapshot?.latestRiskTimestamp, snapshot?.visibleAlerts],
  );

  const freshnessFeeds = useMemo(
    () => [
      {
        title: "Rainfall Ingestion (CHIRPS)",
        subtitle: "Source: NOAA satellite data",
        status: riskFreshness.label,
        detail: riskFreshness.detail,
        tone: riskFreshness.tone,
        icon: <CloudRain className="size-4" aria-hidden="true" />,
      },
      {
        title: "Health Facility Reports (DHIS2)",
        subtitle: "Sync failure at 04:00 AM",
        status: "6h 12m ago",
        detail: "Stale data",
        tone: "danger" as const,
        icon: <ShieldAlert className="size-4" aria-hidden="true" />,
      },
      {
        title: "CHV Daily Screenings",
        subtitle: "Live USSD stream",
        status: snapshot?.latestAlertTimestamp ? formatRelativeLabel(snapshot.latestAlertTimestamp) : "Real-time",
        detail: "Syncing",
        tone: alertFreshness.isStale ? "warning" as const : "success" as const,
        icon: <Waves className="size-4" aria-hidden="true" />,
      },
    ],
    [alertFreshness.isStale, riskFreshness.detail, riskFreshness.label, riskFreshness.tone, snapshot?.latestAlertTimestamp],
  );

  const pipelines = [
    { name: "Daily Weather ETL", state: "Running", tone: "success" as const },
    { name: "Monthly Malaria Profile", state: "Idle", tone: "default" as const },
    { name: "Risk Scoring Engine", state: "Failed (Retrying)", tone: "danger" as const },
    { name: "Alert Trigger Job", state: "Success", tone: "success" as const },
  ];

  const integrations = [
    {
      group: "SMS Gateway",
      name: "Saf-Tel Connect",
      note: "Latency: 340ms",
      tone: "success" as const,
      icon: <BellRing className="size-4" aria-hidden="true" />,
    },
    {
      group: "DHIS2 Sync",
      name: "MOH instance",
      note: "Auth error",
      tone: "danger" as const,
      icon: <DatabaseZap className="size-4" aria-hidden="true" />,
    },
    {
      group: "Weather API",
      name: "OpenWeather Map",
      note: "Status: OK",
      tone: "success" as const,
      icon: <CloudRain className="size-4" aria-hidden="true" />,
    },
    {
      group: "USSD Hub",
      name: "Africa's Talking",
      note: "Channel: Active",
      tone: "success" as const,
      icon: <Waypoints className="size-4" aria-hidden="true" />,
    },
  ];

  const systemEvents = [
    {
      time: snapshot?.latestAlertTimestamp ?? null,
      level: "INFO",
      message: "CHV data payload processed successfully for Suna West ward.",
      tone: "success" as const,
    },
    {
      time: snapshot?.latestRiskTimestamp ?? null,
      level: "ERROR",
      message: "Failed to sync with DHIS2. Connection timeout on endpoint /api/dataValues.",
      tone: "danger" as const,
    },
    {
      time: new Date(Date.now() - 56 * 60 * 1000).toISOString(),
      level: "WARN",
      message: "High memory usage on ingestion node `prod-02`. Current: 88%.",
      tone: "warning" as const,
    },
    {
      time: new Date(Date.now() - 84 * 60 * 1000).toISOString(),
      level: "INFO",
      message: "Automated weekly risk report generated for Migori County director.",
      tone: "success" as const,
    },
    {
      time: new Date(Date.now() - 95 * 60 * 1000).toISOString(),
      level: "INFO",
      message: "Heartbeat signal received from USSD gateway connector.",
      tone: "success" as const,
    },
  ];

  if (!currentUser) {
    return null;
  }

  return (
    <div className="space-y-6">
      <DashboardTopbar
        title="System Status"
        subtitle="Monitor platform health, data pipelines, and integrations"
        lastUpdatedLabel={lastUpdatedLabel}
        lastUpdatedTone={riskFreshness.isStale || alertFreshness.isStale ? "stale" : "default"}
        onRefresh={() => {
          void systemQuery.refetch();
        }}
      />

      <RoleGate
        allowedRoles={["ADMIN", "ANALYST"]}
        title="System view is role-restricted"
        message="Only Admin and Analyst roles should access the operational system-status workspace."
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
                description="Monitor the most important upstream feeds before treating dashboard outputs as current."
              />
              <Button variant="secondary" className="h-10 rounded-pill px-4">
                <RefreshCcw className="mr-2 size-4" aria-hidden="true" />
                Re-sync all
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
                <h2 className="text-xl font-semibold tracking-[-0.03em]">Admin Controls</h2>
                <p className="mt-1 text-sm text-white/74">Operational tools for the control room.</p>
              </div>
            </div>

            <div className="mt-5 space-y-3">
              {[
                { label: "Retry Failed Jobs", icon: <RotateCcw className="size-4" aria-hidden="true" /> },
                { label: "Trigger Manual Risk Scoring", icon: <Gauge className="size-4" aria-hidden="true" /> },
                { label: "Pause Alert System", icon: <PauseCircle className="size-4" aria-hidden="true" /> },
              ].map((action) => (
                <button
                  key={action.label}
                  type="button"
                  className="flex w-full items-center justify-between rounded-[1.25rem] border border-white/12 bg-white/10 px-4 py-3 text-left transition hover:bg-white/14"
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
              <p className="text-[0.68rem] font-semibold uppercase tracking-[0.18em] text-white/60">System version</p>
              <p className="mt-2 text-sm font-semibold">v2.4.9-stable</p>
              <p className="mt-1 text-xs text-white/64">Build b4a2f1</p>
            </div>
          </Card>
        </section>

        <section className="grid gap-6 xl:grid-cols-2">
          <Card className="rounded-[2rem] px-5 py-5 sm:px-6">
            <PageSectionHeader
              className="gap-1"
              title="Pipeline Status"
              description="Quick read on scheduled jobs and scoring workflows."
            />

            <div className="mt-5 space-y-3">
              {pipelines.map((pipeline) => (
                <div key={pipeline.name} className="flex items-center justify-between gap-4 rounded-[1.2rem] px-1 py-1">
                  <div className="flex items-center gap-3">
                    <span
                      className={cn(
                        "size-2.5 rounded-full",
                        pipeline.tone === "success" && "bg-[color:var(--success)]",
                        pipeline.tone === "danger" && "bg-[color:var(--danger)]",
                        pipeline.tone === "default" && "bg-[var(--dashboard-subtle-copy)]",
                      )}
                    />
                    <span className="text-sm font-medium text-panel-copy">{pipeline.name}</span>
                  </div>
                  <StatusBadge
                    tone={pipeline.tone === "danger" ? "danger" : pipeline.tone === "success" ? "success" : "default"}
                    className="px-3 py-1 tracking-[0.14em]"
                  >
                    {pipeline.state}
                  </StatusBadge>
                </div>
              ))}
            </div>
          </Card>

          <Card className="rounded-[2rem] px-5 py-5 sm:px-6">
            <PageSectionHeader
              className="gap-1"
              title="Integrations"
              description="Status of outbound channels and upstream dependencies."
            />

            <div className="mt-5 grid gap-3 sm:grid-cols-2">
              {integrations.map((integration) => (
                <div key={`${integration.group}-${integration.name}`} className="rounded-[1.35rem] border border-panel-table-wrap px-4 py-4">
                  <div className="flex items-start justify-between gap-3">
                    <span
                      className={cn(
                        "inline-flex size-9 items-center justify-center rounded-xl",
                        integration.tone === "success" &&
                          "bg-[color-mix(in_srgb,var(--success)_14%,white)] text-[color:var(--success)] dark:bg-[color-mix(in_srgb,var(--success)_20%,transparent)]",
                        integration.tone === "danger" &&
                          "bg-[color-mix(in_srgb,var(--danger)_14%,white)] text-[color:var(--danger)] dark:bg-[color-mix(in_srgb,var(--danger)_20%,transparent)]",
                      )}
                    >
                      {integration.icon}
                    </span>
                    <span
                      className={cn(
                        "mt-1 size-2 rounded-full",
                        integration.tone === "success" && "bg-[color:var(--success)]",
                        integration.tone === "danger" && "bg-[color:var(--danger)]",
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
                      integration.tone === "danger" && "text-[color:var(--danger)]",
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
              title="System Event Logs"
              description="Latest pipeline, sync, and runtime events for operators."
            />
            <div className="flex flex-wrap items-center gap-2">
              <div className="flex h-10 min-w-[12rem] items-center rounded-pill border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] px-4 text-sm text-panel-muted">
                Search logs...
              </div>
              <div className="flex h-10 items-center rounded-pill border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] px-4 text-sm text-panel-copy">
                All levels
              </div>
            </div>
          </div>

          <div className="mt-5 overflow-hidden rounded-[1.4rem] border border-panel-table-wrap">
            <div className="divide-y divide-[var(--dashboard-table-line)]">
              {systemEvents.map((event, index) => (
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
              ))}
            </div>
          </div>

          <div className="mt-5 flex flex-wrap items-center gap-4 text-sm text-panel-muted">
            <span className="inline-flex items-center gap-2">
              <Logs className="size-4" aria-hidden="true" />
              Audit trail retained for operational review.
            </span>
            <span className="inline-flex items-center gap-2">
              <MapPinned className="size-4" aria-hidden="true" />
              Visible scope: {isLoading ? "Loading..." : `${snapshot?.visibleWards ?? 0} wards`}
            </span>
            <span className="inline-flex items-center gap-2">
              <Clock3 className="size-4" aria-hidden="true" />
              Alert freshness: {alertFreshness.detail}
            </span>
          </div>
        </Card>
      </RoleGate>
    </div>
  );
}
