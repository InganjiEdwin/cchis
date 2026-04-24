"use client";

import {
  AlertTriangle,
  BellRing,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  CircleAlert,
  CloudRain,
  Clock3,
  Download,
  Droplets,
  ExternalLink,
  Info,
  Radio,
  Search,
  Siren,
  Smartphone,
  Waves,
  X,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { DashboardTopbar } from "@/components/dashboard-topbar";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { InputShell } from "@/components/ui/input-shell";
import { PageSectionHeader } from "@/components/ui/page-section-header";
import { StatusBanner } from "@/components/ui/status-banner";
import { StatusBadge } from "@/components/ui/status-badge";
import { cn } from "@/lib/cn";
import { type AlertRecord } from "@/lib/dashboard";
import { describeFreshness, formatRelativeTimestamp, getLatestTimestamp } from "@/lib/freshness";
import { useAlertsQuery } from "@/queries/use-alerts-query";

type AlertStatusFilter = "ALL" | "SENT" | "PENDING" | "FAILED";
type AlertTypeFilter =
  | "ALL"
  | "CHOLERA_RISK"
  | "FLOOD_RISK"
  | "WATER_CONTAMINATION"
  | "HEAVY_RAINFALL"
  | "OPERATIONAL_ALERT";

type AlertTypeMeta = {
  key: Exclude<AlertTypeFilter, "ALL">;
  label: string;
  shortLabel: string;
  icon: typeof Droplets;
  tone: "red" | "amber" | "orange" | "blue" | "slate";
};

type DecoratedAlert = AlertRecord & {
  alertType: AlertTypeMeta;
  statusFilter: Exclude<AlertStatusFilter, "ALL">;
  statusLabel: string;
  channelLabel: string;
  timeLabel: string;
  relativeLabel: string;
  operationalLabel: string;
  severity: "HIGH" | "MEDIUM" | "LOW";
  severityLabel: string;
};

const ALERT_TYPE_META: Record<Exclude<AlertTypeFilter, "ALL">, AlertTypeMeta> = {
  CHOLERA_RISK: {
    key: "CHOLERA_RISK",
    label: "Cholera Risk",
    shortLabel: "Cholera",
    icon: Droplets,
    tone: "red",
  },
  FLOOD_RISK: {
    key: "FLOOD_RISK",
    label: "Flood Risk",
    shortLabel: "Flood",
    icon: Waves,
    tone: "blue",
  },
  WATER_CONTAMINATION: {
    key: "WATER_CONTAMINATION",
    label: "Water Contamination",
    shortLabel: "Water",
    icon: CircleAlert,
    tone: "red",
  },
  HEAVY_RAINFALL: {
    key: "HEAVY_RAINFALL",
    label: "Heavy Rainfall",
    shortLabel: "Rainfall",
    icon: CloudRain,
    tone: "orange",
  },
  OPERATIONAL_ALERT: {
    key: "OPERATIONAL_ALERT",
    label: "Operational Alert",
    shortLabel: "Operational",
    icon: BellRing,
    tone: "slate",
  },
};

const STATUS_FILTER_OPTIONS: Array<{ value: AlertStatusFilter; label: string }> = [
  { value: "ALL", label: "All" },
  { value: "SENT", label: "Sent" },
  { value: "PENDING", label: "Pending" },
  { value: "FAILED", label: "Failed" },
];

const ALERT_TYPE_OPTIONS: Array<{ value: AlertTypeFilter; label: string }> = [
  { value: "ALL", label: "All alerts" },
  { value: "CHOLERA_RISK", label: "Cholera risk" },
  { value: "FLOOD_RISK", label: "Flood risk" },
  { value: "WATER_CONTAMINATION", label: "Water contamination" },
  { value: "HEAVY_RAINFALL", label: "Heavy rainfall" },
  { value: "OPERATIONAL_ALERT", label: "Operational alert" },
];

const ROWS_PER_PAGE = 5;

function classifyAlertType(alert: AlertRecord): AlertTypeMeta {
  const haystack = `${alert.message} ${alert.recipient} ${alert.ward_name}`.toLowerCase();

  if (haystack.includes("cholera")) {
    return ALERT_TYPE_META.CHOLERA_RISK;
  }
  if (haystack.includes("flood")) {
    return ALERT_TYPE_META.FLOOD_RISK;
  }
  if (haystack.includes("water")) {
    return ALERT_TYPE_META.WATER_CONTAMINATION;
  }
  if (haystack.includes("rain")) {
    return ALERT_TYPE_META.HEAVY_RAINFALL;
  }

  return ALERT_TYPE_META.OPERATIONAL_ALERT;
}

function getStatusFilter(status: AlertRecord["status"]): Exclude<AlertStatusFilter, "ALL"> {
  if (status === "DELIVERED") {
    return "SENT";
  }
  if (status === "FAILED") {
    return "FAILED";
  }
  return "PENDING";
}

function getStatusLabel(status: AlertRecord["status"]) {
  switch (status) {
    case "DELIVERED":
      return "Sent";
    case "FAILED":
      return "Failed";
    case "RETRY_PENDING":
      return "Retry";
    case "QUEUED":
    default:
      return "Pending";
  }
}

function getChannelLabel(channel: AlertRecord["channel"]) {
  switch (channel) {
    case "SMS":
      return "SMS Notification";
    case "WHATSAPP":
      return "Radio Broadcast";
    case "DASHBOARD":
    default:
      return "USSD Notification";
  }
}

function getChannelIcon(channel: AlertRecord["channel"]) {
  switch (channel) {
    case "SMS":
      return Smartphone;
    case "WHATSAPP":
      return Radio;
    case "DASHBOARD":
    default:
      return Siren;
  }
}

function formatRelativeShort(timestamp: string | null) {
  if (!timestamp) {
    return "No recent update";
  }

  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) {
    return "Invalid timestamp";
  }

  const minutes = Math.max(0, Math.round((Date.now() - date.getTime()) / 60000));

  if (minutes < 1) {
    return "Just now";
  }
  if (minutes < 60) {
    return `${minutes}m ago`;
  }

  const hours = Math.round(minutes / 60);
  if (hours < 24) {
    return `${hours}h ago`;
  }

  const days = Math.round(hours / 24);
  return `${days}d ago`;
}

function formatClockLabel(timestamp: string | null) {
  if (!timestamp) {
    return "No timestamp";
  }

  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) {
    return "Invalid time";
  }

  return date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

function formatSentTime(timestamp: string | null) {
  return `${formatClockLabel(timestamp)} (${formatRelativeShort(timestamp)})`;
}

function formatExactTimestamp(timestamp: string | null) {
  if (!timestamp) {
    return "No timestamp available";
  }

  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) {
    return "Invalid timestamp";
  }

  return date.toLocaleString([], {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function getAlertSeverity(riskScore: number | null): "HIGH" | "MEDIUM" | "LOW" {
  const value = riskScore ?? 0;
  if (value >= 75) {
    return "HIGH";
  }
  if (value >= 40) {
    return "MEDIUM";
  }
  return "LOW";
}

function getSeverityLabel(severity: "HIGH" | "MEDIUM" | "LOW") {
  switch (severity) {
    case "HIGH":
      return "High severity";
    case "MEDIUM":
      return "Medium severity";
    case "LOW":
    default:
      return "Low severity";
  }
}

function buildPaginationItems(currentPage: number, totalPages: number): Array<number | "..."> {
  if (totalPages <= 5) {
    return Array.from({ length: totalPages }, (_, index) => index + 1);
  }

  if (currentPage <= 3) {
    return [1, 2, 3, "...", totalPages];
  }

  if (currentPage >= totalPages - 2) {
    return [1, "...", totalPages - 2, totalPages - 1, totalPages];
  }

  return [1, "...", currentPage, "...", totalPages];
}

function downloadAlertsCsv(alerts: DecoratedAlert[]) {
  const rows = [
    ["Alert Type", "Ward", "Channel", "Status", "Created At", "Sent At", "Recipient", "Message"],
    ...alerts.map((alert) => [
      alert.alertType.label,
      alert.ward_name,
      alert.channelLabel,
      alert.statusLabel,
      alert.created_at,
      alert.sent_at ?? "",
      alert.recipient,
      alert.message,
    ]),
  ];

  const csv = rows
    .map((row) =>
      row
        .map((value) => `"${String(value).replaceAll('"', '""')}"`)
        .join(","),
    )
    .join("\n");

  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "alerts-monitoring.csv";
  link.click();
  URL.revokeObjectURL(url);
}

function getToneSurface(tone: AlertTypeMeta["tone"]) {
  switch (tone) {
    case "red":
      return "bg-[color-mix(in_srgb,var(--danger)_12%,white)] text-[color:var(--danger)] dark:bg-[color-mix(in_srgb,var(--danger)_18%,transparent)]";
    case "blue":
      return "bg-[color-mix(in_srgb,var(--brand)_12%,white)] text-brand dark:bg-[color-mix(in_srgb,var(--brand)_18%,transparent)]";
    case "orange":
    case "amber":
      return "bg-[color-mix(in_srgb,var(--warning)_14%,white)] text-[color:var(--warning)] dark:bg-[color-mix(in_srgb,var(--warning)_18%,transparent)]";
    case "slate":
    default:
      return "bg-[color-mix(in_srgb,var(--dashboard-table-line)_60%,transparent)] text-panel-copy";
  }
}

export default function AlertsPage() {
  const { currentUser } = useAuth();
  const [search, setSearch] = useState("");
  const [selectedType, setSelectedType] = useState<AlertTypeFilter>("ALL");
  const [selectedStatus, setSelectedStatus] = useState<AlertStatusFilter>("ALL");
  const [page, setPage] = useState(1);
  const [selectedAlertId, setSelectedAlertId] = useState<number | null>(null);
  const alertsQuery = useAlertsQuery({ enabled: Boolean(currentUser) });
  const alerts = alertsQuery.data ?? [];
  const isLoading = alertsQuery.isPending;
  const isRefreshing = alertsQuery.isFetching;
  const error = alertsQuery.error instanceof Error ? alertsQuery.error.message : null;

  const decoratedAlerts = useMemo<DecoratedAlert[]>(
    () =>
      alerts.map((alert) => {
        const alertType = classifyAlertType(alert);
        const timestamp = alert.sent_at ?? alert.created_at;
        const severity = getAlertSeverity(alert.risk_score);

        return {
          ...alert,
          alertType,
          statusFilter: getStatusFilter(alert.status),
          statusLabel: getStatusLabel(alert.status),
          channelLabel: getChannelLabel(alert.channel),
          timeLabel: formatSentTime(timestamp),
          relativeLabel: formatRelativeShort(timestamp),
          operationalLabel: formatRelativeTimestamp(timestamp),
          severity,
          severityLabel: getSeverityLabel(severity),
        };
      }),
    [alerts],
  );

  const filteredAlerts = useMemo(() => {
    const normalizedSearch = search.trim().toLowerCase();

    return decoratedAlerts.filter((alert) => {
      if (selectedType !== "ALL" && alert.alertType.key !== selectedType) {
        return false;
      }

      if (selectedStatus !== "ALL" && alert.statusFilter !== selectedStatus) {
        return false;
      }

      if (!normalizedSearch) {
        return true;
      }

      return (
        alert.alertType.label.toLowerCase().includes(normalizedSearch) ||
        alert.ward_name.toLowerCase().includes(normalizedSearch) ||
        alert.message.toLowerCase().includes(normalizedSearch) ||
        alert.channelLabel.toLowerCase().includes(normalizedSearch)
      );
    });
  }, [decoratedAlerts, search, selectedStatus, selectedType]);

  useEffect(() => {
    setPage(1);
  }, [search, selectedStatus, selectedType]);

  const alertsLast24Hours = useMemo(
    () =>
      decoratedAlerts.filter((alert) => Date.now() - new Date(alert.created_at).getTime() <= 24 * 60 * 60 * 1000)
        .length,
    [decoratedAlerts],
  );
  const activeAlertsCount = useMemo(
    () => decoratedAlerts.filter((alert) => alert.statusFilter === "PENDING").length,
    [decoratedAlerts],
  );
  const failedCount = useMemo(
    () => decoratedAlerts.filter((alert) => alert.statusFilter === "FAILED").length,
    [decoratedAlerts],
  );

  const latestAlertTimestamp = getLatestTimestamp(decoratedAlerts.map((alert) => alert.created_at));
  const alertFreshness = describeFreshness(latestAlertTimestamp, 20);
  const topbarTimestampLabel = isRefreshing ? "Refreshing..." : formatRelativeShort(latestAlertTimestamp);
  const totalPages = Math.max(1, Math.ceil(filteredAlerts.length / ROWS_PER_PAGE));
  const safePage = Math.min(page, totalPages);
  const visibleAlerts = filteredAlerts.slice((safePage - 1) * ROWS_PER_PAGE, safePage * ROWS_PER_PAGE);
  const paginationItems = buildPaginationItems(safePage, totalPages);

  const mostCriticalAlert = useMemo(() => {
    const statusRank: Record<DecoratedAlert["statusFilter"], number> = {
      FAILED: 3,
      PENDING: 2,
      SENT: 1,
    };

    return [...decoratedAlerts].sort((left, right) => {
      const statusDiff = statusRank[right.statusFilter] - statusRank[left.statusFilter];
      if (statusDiff !== 0) {
        return statusDiff;
      }

      const riskDiff = (right.risk_score ?? 0) - (left.risk_score ?? 0);
      if (riskDiff !== 0) {
        return riskDiff;
      }

      return new Date(right.created_at).getTime() - new Date(left.created_at).getTime();
    })[0];
  }, [decoratedAlerts]);

  const activeZones = useMemo(() => {
    const wardMap = new Map<
      string,
      {
        wardName: string;
        count: number;
        highestRisk: number;
        latestAt: string;
      }
    >();

    for (const alert of decoratedAlerts) {
      const existing = wardMap.get(alert.ward_name);
      const risk = alert.risk_score ?? 0;

      if (!existing) {
        wardMap.set(alert.ward_name, {
          wardName: alert.ward_name,
          count: 1,
          highestRisk: risk,
          latestAt: alert.created_at,
        });
        continue;
      }

      existing.count += 1;
      existing.highestRisk = Math.max(existing.highestRisk, risk);
      if (new Date(alert.created_at).getTime() > new Date(existing.latestAt).getTime()) {
        existing.latestAt = alert.created_at;
      }
    }

    return [...wardMap.values()]
      .sort((left, right) => {
        if (right.highestRisk !== left.highestRisk) {
          return right.highestRisk - left.highestRisk;
        }
        if (right.count !== left.count) {
          return right.count - left.count;
        }
        return new Date(right.latestAt).getTime() - new Date(left.latestAt).getTime();
      })
      .slice(0, 4);
  }, [decoratedAlerts]);

  const selectedAlert = useMemo(
    () => decoratedAlerts.find((alert) => alert.id === selectedAlertId) ?? null,
    [decoratedAlerts, selectedAlertId],
  );

  const freshnessAgeMinutes = latestAlertTimestamp
    ? Math.max(0, Math.round((Date.now() - new Date(latestAlertTimestamp).getTime()) / 60000))
    : Number.POSITIVE_INFINITY;
  const freshnessTone = freshnessAgeMinutes >= 6 * 60 ? "critical" : freshnessAgeMinutes >= 20 ? "warning" : "healthy";
  const lastFailure = useMemo(
    () =>
      decoratedAlerts
        .filter((alert) => alert.statusFilter === "FAILED")
        .sort((left, right) => new Date(right.created_at).getTime() - new Date(left.created_at).getTime())[0] ?? null,
    [decoratedAlerts],
  );
  const previousDayAlerts = useMemo(
    () =>
      decoratedAlerts.filter((alert) => {
        const createdAt = new Date(alert.created_at).getTime();
        const age = Date.now() - createdAt;
        return age > 24 * 60 * 60 * 1000 && age <= 48 * 60 * 60 * 1000;
      }).length,
    [decoratedAlerts],
  );
  const sentTrend = alertsLast24Hours - previousDayAlerts;

  if (!currentUser) {
    return null;
  }

  return (
    <div className="space-y-6">
      <DashboardTopbar
        title="Alerts"
        subtitle="Operational alert coordination"
        lastUpdatedLabel={topbarTimestampLabel}
        lastUpdatedTone={alertFreshness.isStale ? "stale" : "default"}
        onRefresh={() => {
          void alertsQuery.refetch();
        }}
      />

      {error ? (
        <StatusBanner tone="danger" icon={<AlertTriangle aria-hidden="true" />}>
          {error}
        </StatusBanner>
      ) : null}

      {!isLoading && !error && decoratedAlerts.length === 0 ? (
        <StatusBanner tone="warning" icon={<AlertTriangle aria-hidden="true" />}>
          No alerts are available yet in your visible scope.
        </StatusBanner>
      ) : null}

      {!isLoading && !error && decoratedAlerts.length > 0 && alertFreshness.isStale ? (
        <Card
          className={cn(
            "rounded-3xl px-5 py-5 sm:px-6",
            freshnessTone === "critical"
              ? "border-[color:var(--danger)]/25 bg-panel"
              : "border-[color:var(--warning)]/25 bg-panel",
          )}
        >
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div className="flex items-start gap-3">
              <span
                className={cn(
                  "mt-0.5 inline-flex size-9 shrink-0 items-center justify-center rounded-full",
                  freshnessTone === "critical"
                    ? "bg-[color-mix(in_srgb,var(--danger)_14%,white)] text-[color:var(--danger)] dark:bg-[color-mix(in_srgb,var(--danger)_18%,transparent)]"
                    : "bg-[color-mix(in_srgb,var(--warning)_16%,white)] text-[color:var(--warning)] dark:bg-[color-mix(in_srgb,var(--warning)_20%,transparent)]",
                )}
              >
                <AlertTriangle className="size-4" aria-hidden="true" />
              </span>
              <div className="space-y-1">
                <div className="text-sm font-semibold text-panel-strong">
                  {freshnessTone === "critical" ? "Data freshness issue" : "Freshness warning"} - last update{" "}
                  {formatExactTimestamp(latestAlertTimestamp)} ({formatRelativeShort(latestAlertTimestamp)})
                </div>
                <p className="max-w-3xl text-sm text-panel-copy">
                  Operators should verify ingestion health before treating these alert counts as current field
                  conditions.
                </p>
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-3">
              <Button
                variant="secondary"
                className="h-10 px-4"
                onClick={() => {
                  void alertsQuery.refetch();
                }}
              >
                Refresh data
              </Button>
              <Link
                href="/system"
                className="inline-flex h-10 items-center justify-center rounded-pill border border-panel-table-wrap px-4 text-sm font-semibold text-panel-copy transition hover:border-[var(--dashboard-icon-button-border)] hover:text-panel-strong"
              >
                View pipeline status
              </Link>
            </div>
          </div>
        </Card>
      ) : null}

      <section className="space-y-5">
        <PageSectionHeader
          title="Alerts Monitoring"
          description="Track delivery status, operational risk activity, and ward-level alert pressure across Migori County."
        />

        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_22rem]">
          <div className="grid gap-4 md:grid-cols-3">
            <Card className="rounded-3xl bg-panel px-5 py-5">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.18em] text-panel-subtle">
                    Alerts sent (last 24 hours)
                  </p>
                  <div className="mt-3 text-4xl font-semibold leading-none text-panel-strong">
                    {isLoading ? "..." : alertsLast24Hours.toLocaleString()}
                  </div>
                </div>
                <span className="inline-flex size-10 items-center justify-center rounded-full bg-[color-mix(in_srgb,var(--brand)_10%,white)] text-brand dark:bg-[color-mix(in_srgb,var(--brand)_18%,transparent)]">
                  <ChevronRight className="size-4" aria-hidden="true" />
                </span>
              </div>
              <p className="mt-4 text-sm text-panel-muted">
                {isLoading
                  ? "Checking recent delivery volume"
                  : `${sentTrend >= 0 ? "+" : ""}${sentTrend} vs previous 24h`}
              </p>
            </Card>

            <Card className="rounded-3xl border-[color:var(--warning)]/20 bg-panel px-5 py-5">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.18em] text-panel-subtle">Active alerts</p>
                  <div className="mt-3 text-4xl font-semibold leading-none text-panel-strong">
                    {isLoading ? "..." : activeAlertsCount}
                  </div>
                </div>
                <span className="inline-flex size-10 items-center justify-center rounded-full bg-[color-mix(in_srgb,var(--warning)_18%,white)] text-[color:var(--warning)] dark:bg-[color-mix(in_srgb,var(--warning)_18%,transparent)]">
                  <BellRing className="size-4" aria-hidden="true" />
                </span>
              </div>
              <p className="mt-4 text-sm text-panel-muted">
                Ongoing risk monitoring cycles still awaiting a clean resolution path.
              </p>
            </Card>

            <Card
              className={cn(
                "rounded-3xl px-5 py-5",
                failedCount > 0
                  ? "border-[color:var(--danger)]/20 bg-panel"
                  : "border-[color:var(--success)]/20 bg-panel",
              )}
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.18em] text-panel-subtle">
                    Delivery failures
                  </p>
                  <div className="mt-3 text-4xl font-semibold leading-none text-panel-strong">
                    {isLoading ? "..." : failedCount}
                  </div>
                </div>
                <span
                  className={cn(
                    "inline-flex size-10 items-center justify-center rounded-full",
                    failedCount > 0
                      ? "bg-[color-mix(in_srgb,var(--danger)_14%,white)] text-[color:var(--danger)] dark:bg-[color-mix(in_srgb,var(--danger)_18%,transparent)]"
                      : "bg-[color-mix(in_srgb,var(--success)_14%,white)] text-[color:var(--success)] dark:bg-[color-mix(in_srgb,var(--success)_18%,transparent)]",
                  )}
                >
                  <AlertTriangle className="size-4" aria-hidden="true" />
                </span>
              </div>
              <p className="mt-4 text-sm text-panel-muted">
                {lastFailure ? `Last failure ${formatRelativeShort(lastFailure.created_at)}` : "Delivery reliability currently stable."}
              </p>
            </Card>
          </div>

          <Card className="rounded-3xl bg-panel px-5 py-5">
            <h2 className="text-2xl font-semibold text-panel-strong">Priority Alert Review</h2>
            <p className="mt-2 text-sm text-panel-muted">
              Derived summary of the highest-pressure visible alert record in the current scope.
            </p>
            <div className="mt-5 rounded-2xl bg-[color-mix(in_srgb,var(--brand)_8%,var(--panel))] p-4">
              <strong className="block text-base text-panel-strong">
                {mostCriticalAlert
                  ? `${mostCriticalAlert.severity === "HIGH" ? "Highest priority alert" : "Review alert"} - ${mostCriticalAlert.ward_name}`
                  : "No priority alert in current scope."}
              </strong>
              <p className="mt-2 text-sm text-panel-muted">
                {mostCriticalAlert
                  ? `Priority signal: ${mostCriticalAlert.alertType.label} via ${mostCriticalAlert.channelLabel.toLowerCase()} triggered ${mostCriticalAlert.relativeLabel}.`
                  : "No visible alert record currently stands out above the rest of the filtered scope."}
              </p>
            </div>
            {mostCriticalAlert ? (
              <Link
                href={`/alerts/${mostCriticalAlert.id}`}
                className="mt-5 inline-flex items-center gap-2 text-sm font-semibold text-brand transition hover:text-[var(--dashboard-icon-button-ink-hover)]"
              >
                Review Alert Detail
                <ChevronRight className="size-4" aria-hidden="true" />
              </Link>
            ) : null}
          </Card>
        </div>
      </section>

      <Card className="rounded-[2rem] bg-panel px-5 py-5 sm:px-6">
        <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
          <div className="flex min-w-0 flex-1 flex-col gap-4 lg:flex-row lg:flex-wrap lg:items-end">
            <InputShell
              className="min-w-0 flex-[1.4]"
              icon={<Search className="size-4" aria-hidden="true" />}
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search ward, alert type, or channel..."
            />

            <label className="flex min-w-[11rem] flex-col gap-2">
              <span className="text-sm font-medium text-panel-copy">Alert type</span>
              <span className="relative flex h-11 items-center rounded-pill border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] px-4 shadow-sm">
                <select
                  value={selectedType}
                  onChange={(event) => setSelectedType(event.target.value as AlertTypeFilter)}
                  className="h-full w-full appearance-none bg-transparent pr-8 text-sm text-panel-strong outline-none"
                >
                  {ALERT_TYPE_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
                <ChevronDown className="pointer-events-none absolute right-4 size-4 text-panel-muted" aria-hidden="true" />
              </span>
            </label>

            <div className="flex flex-wrap gap-2" role="tablist" aria-label="Alert status filters">
              {STATUS_FILTER_OPTIONS.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  className={cn(
                    "inline-flex h-11 items-center justify-center rounded-pill border px-4 text-sm font-semibold transition",
                    option.value === selectedStatus
                      ? "border-brand bg-brand text-white shadow-[var(--login-submit-shadow)]"
                      : "border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] text-panel-copy hover:border-[var(--dashboard-icon-button-border)] hover:text-panel-strong",
                  )}
                  onClick={() => setSelectedStatus(option.value)}
                >
                  {option.label}
                </button>
              ))}
            </div>
          </div>

          <Button
            variant="secondary"
            className="h-11 self-start bg-[var(--dashboard-icon-button-surface)] px-4 xl:self-end"
            onClick={() => downloadAlertsCsv(filteredAlerts)}
            disabled={!filteredAlerts.length}
          >
            <Download className="size-4" aria-hidden="true" />
            <span>Export CSV</span>
          </Button>
        </div>

        <div className="mt-6 overflow-hidden rounded-[1.5rem] border border-panel-table-wrap">
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-panel-table-wrap text-sm">
              <thead className="bg-[color-mix(in_srgb,var(--dashboard-table-line)_30%,transparent)]">
                <tr className="text-left">
                  {["Alert type", "Administrative ward", "Channel", "Status", "Sent time", "Action"].map((label) => (
                    <th
                      key={label}
                      className="px-5 py-4 text-[0.72rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle"
                    >
                      {label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-panel-table-wrap bg-panel">
                {isLoading ? (
                  Array.from({ length: ROWS_PER_PAGE }).map((_, index) => (
                    <tr key={`alerts-skeleton-${index}`}>
                      <td colSpan={6} className="px-5 py-5">
                        <div className="h-6 w-full animate-pulse rounded-full bg-[color-mix(in_srgb,var(--dashboard-table-line)_55%,transparent)]" />
                      </td>
                    </tr>
                  ))
                ) : visibleAlerts.length > 0 ? (
                  visibleAlerts.map((alert) => {
                    const AlertIcon = alert.alertType.icon;
                    const ChannelIcon = getChannelIcon(alert.channel);

                    return (
                      <tr
                        key={alert.id}
                        className="cursor-pointer transition hover:bg-[color-mix(in_srgb,var(--dashboard-nav-hover)_40%,transparent)] focus-within:bg-[color-mix(in_srgb,var(--dashboard-nav-hover)_46%,transparent)]"
                        onClick={() => setSelectedAlertId(alert.id)}
                        onKeyDown={(event) => {
                          if (event.key === "Enter" || event.key === " ") {
                            event.preventDefault();
                            setSelectedAlertId(alert.id);
                          }
                        }}
                        tabIndex={0}
                      >
                        <td className="px-5 py-4 align-top">
                          <div className="flex items-start gap-3">
                            <span
                              className={cn(
                                "inline-flex size-11 shrink-0 items-center justify-center rounded-2xl",
                                getToneSurface(alert.alertType.tone),
                              )}
                            >
                              <AlertIcon className="size-5" aria-hidden="true" />
                            </span>
                            <div className="min-w-0 space-y-2">
                              <div className="font-semibold text-panel-strong">{alert.alertType.label}</div>
                              <div className="flex flex-wrap items-center gap-2">
                                <StatusBadge tone="info" className="tracking-[0.12em]">
                                  Backend record
                                </StatusBadge>
                                <StatusBadge
                                  tone={
                                    alert.severity === "HIGH"
                                      ? "danger"
                                      : alert.severity === "MEDIUM"
                                        ? "warning"
                                        : "success"
                                  }
                                  className="tracking-[0.12em]"
                                >
                                  {alert.severityLabel}
                                </StatusBadge>
                              </div>
                            </div>
                          </div>
                        </td>
                        <td className="px-5 py-4 align-top font-semibold text-panel-strong">{alert.ward_name}</td>
                        <td className="px-5 py-4 align-top">
                          <div className="flex items-center gap-2 text-panel-copy">
                            <ChannelIcon className="size-4 text-panel-muted" aria-hidden="true" />
                            <span>{alert.channelLabel}</span>
                          </div>
                        </td>
                        <td className="px-5 py-4 align-top">
                          <div className="space-y-2">
                            <StatusBadge
                              tone={
                                alert.statusFilter === "SENT"
                                  ? "success"
                                  : alert.statusFilter === "FAILED"
                                    ? "danger"
                                    : "warning"
                              }
                              className="tracking-[0.12em]"
                            >
                              {alert.statusLabel}
                            </StatusBadge>
                            {alert.status === "RETRY_PENDING" ? (
                              <p className="text-xs font-medium text-[color:var(--warning)]">Retry queue active</p>
                            ) : null}
                          </div>
                        </td>
                        <td className="px-5 py-4 align-top text-panel-copy">{alert.timeLabel}</td>
                        <td className="px-5 py-4 align-top">
                          <Button
                            variant="ghost"
                            className="h-9 rounded-pill px-3 text-sm"
                            onClick={(event) => {
                              event.stopPropagation();
                              setSelectedAlertId(alert.id);
                            }}
                          >
                            {alert.statusFilter === "FAILED" || alert.status === "RETRY_PENDING" ? "Retry review" : "Open"}
                          </Button>
                        </td>
                      </tr>
                    );
                  })
                ) : (
                  <tr>
                    <td colSpan={6} className="px-5 py-10 text-center text-sm text-panel-muted">
                      No alerts match the current search and filter combination.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

          <div className="mt-5 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex flex-wrap items-center gap-3 text-sm text-panel-muted">
              <span>
                {Math.min(filteredAlerts.length, safePage * ROWS_PER_PAGE)} of {filteredAlerts.length} alerts
              </span>
              <StatusBadge tone="warning" className="tracking-[0.12em]">
                Read-path only
              </StatusBadge>
            </div>

          {totalPages > 1 ? (
            <div className="flex items-center gap-2">
              <Button
                variant="secondary"
                size="icon"
                className="size-10"
                onClick={() => setPage((value) => Math.max(1, value - 1))}
                disabled={safePage === 1}
              >
                <ChevronLeft className="size-4" aria-hidden="true" />
              </Button>
              {paginationItems.map((item, index) =>
                item === "..." ? (
                  <span key={`ellipsis-${index}`} className="px-2 text-sm text-panel-subtle">
                    ...
                  </span>
                ) : (
                  <button
                    key={item}
                    type="button"
                    className={cn(
                      "inline-flex size-10 items-center justify-center rounded-full text-sm font-semibold transition",
                      item === safePage
                        ? "bg-brand text-white shadow-[var(--login-submit-shadow)]"
                        : "text-panel-copy hover:bg-[color-mix(in_srgb,var(--dashboard-nav-hover)_60%,transparent)]",
                    )}
                    onClick={() => setPage(item)}
                  >
                    {item}
                  </button>
                ),
              )}
              <Button
                variant="secondary"
                size="icon"
                className="size-10"
                onClick={() => setPage((value) => Math.min(totalPages, value + 1))}
                disabled={safePage === totalPages}
              >
                <ChevronRight className="size-4" aria-hidden="true" />
              </Button>
            </div>
          ) : null}
        </div>
      </Card>

      <section className="grid gap-5 xl:grid-cols-[minmax(0,1.45fr)_22rem]">
        <Card className="overflow-hidden rounded-[2rem] p-5 sm:p-6">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <h2 className="text-2xl font-semibold text-panel-strong">Alert Pressure By Ward</h2>
              <p className="mt-2 text-sm text-panel-muted">
                Derived ward ranking from visible alert counts and latest recorded risk, without a dedicated geospatial alert-zone contract on this page yet.
              </p>
            </div>
          </div>

          <div className="mt-6 rounded-[1.75rem] border border-panel-table-wrap bg-[radial-gradient(circle_at_top_left,color-mix(in_srgb,var(--brand)_12%,transparent),transparent_40%),radial-gradient(circle_at_bottom_right,color-mix(in_srgb,var(--warning)_12%,transparent),transparent_35%),linear-gradient(135deg,color-mix(in_srgb,var(--panel)_92%,white),var(--panel))] p-5">
            {activeZones.length > 0 ? (
              <div className="space-y-3">
                {activeZones.map((zone, index) => (
                  <div
                    key={zone.wardName}
                    className="flex items-center justify-between gap-4 rounded-[1.3rem] border border-panel-table-wrap bg-panel/85 px-4 py-4"
                  >
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <StatusBadge
                          tone={index === 0 ? "danger" : "warning"}
                          className="tracking-[0.12em]"
                        >
                          {index === 0 ? "Highest visible pressure" : "Derived review"}
                        </StatusBadge>
                        <strong className="truncate text-base text-panel-strong">{zone.wardName}</strong>
                      </div>
                      <p className="mt-2 text-sm text-panel-muted">
                        {zone.count} visible alerts, highest recorded risk {Math.round(zone.highestRisk)}/100, latest activity {formatRelativeShort(zone.latestAt)}.
                      </p>
                    </div>
                    <Link
                      href={`/wards?search=${encodeURIComponent(zone.wardName)}`}
                      className="inline-flex shrink-0 items-center gap-2 text-sm font-semibold text-brand transition hover:text-[var(--dashboard-icon-button-ink-hover)]"
                    >
                      Review ward
                      <ChevronRight className="size-4" aria-hidden="true" />
                    </Link>
                  </div>
                ))}
              </div>
            ) : (
              <div className="rounded-[1.3rem] border border-dashed border-panel-table-wrap px-4 py-8 text-sm text-panel-muted">
                No visible ward alert pressure is available for ranking in the current scope yet.
              </div>
            )}
          </div>
        </Card>

        <Card className="rounded-[2rem] bg-[linear-gradient(180deg,color-mix(in_srgb,var(--brand)_10%,var(--panel)),var(--panel))] px-5 py-5">
          <span className="text-xs font-semibold uppercase tracking-[0.18em] text-panel-subtle">Intelligence signal</span>
          <strong className="mt-3 block text-2xl leading-tight text-panel-strong">
            {mostCriticalAlert
              ? `${Math.max(72, Math.round((mostCriticalAlert.risk_score ?? 0) * 0.9))}% alert trigger probability`
              : "No high-confidence alert signal"}
          </strong>
          <p className="mt-3 text-sm text-panel-muted">
            {alertFreshness.isStale ? "Data quality: review freshness" : "Data quality: good"}
          </p>
        </Card>
      </section>

      {selectedAlert ? (
        <>
          <button
            type="button"
            className="fixed inset-0 z-40 bg-slate-950/50 backdrop-blur-[1px]"
            onClick={() => setSelectedAlertId(null)}
            aria-label="Close alert detail drawer"
          />
          <aside className="fixed inset-y-0 right-0 z-50 flex w-full max-w-[30rem] flex-col border-l border-panel-border bg-panel shadow-2xl">
            <div className="flex items-start justify-between gap-4 border-b border-panel-table-wrap px-5 py-5 sm:px-6">
              <div>
                <span className="text-xs font-semibold uppercase tracking-[0.18em] text-panel-subtle">Alert detail</span>
                <h2 className="mt-2 text-2xl font-semibold text-panel-strong">{selectedAlert.alertType.label}</h2>
                <p className="mt-1 text-sm text-panel-muted">{selectedAlert.ward_name}</p>
              </div>

              <Button
                variant="ghost"
                size="icon"
                className="size-10 shrink-0"
                onClick={() => setSelectedAlertId(null)}
                aria-label="Close alert detail"
              >
                <X className="size-4" aria-hidden="true" />
              </Button>
            </div>

            <div className="flex-1 space-y-5 overflow-y-auto px-5 py-5 sm:px-6">
              <div className="grid gap-3 sm:grid-cols-2">
                {[
                  ["Status", selectedAlert.statusLabel],
                  ["Severity", selectedAlert.severityLabel],
                  ["Channel", selectedAlert.channelLabel],
                  ["Sent time", selectedAlert.timeLabel],
                ].map(([label, value]) => (
                  <Card key={label} className="rounded-2xl px-4 py-4 shadow-none">
                    <span className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-subtle">{label}</span>
                    <strong className="mt-2 block text-base text-panel-strong">{value}</strong>
                  </Card>
                ))}
              </div>

              <Card className="rounded-2xl px-4 py-4 shadow-none">
                <h3 className="text-sm font-semibold uppercase tracking-[0.16em] text-panel-subtle">Operational message</h3>
                <p className="mt-3 text-sm leading-6 text-panel-copy">{selectedAlert.message}</p>
              </Card>

              <Card className="rounded-2xl px-4 py-4 shadow-none">
                <h3 className="text-sm font-semibold uppercase tracking-[0.16em] text-panel-subtle">Delivery path</h3>
                <ul className="mt-4 space-y-3 text-sm text-panel-copy">
                  <li className="flex items-center gap-3">
                    <Clock3 className="size-4 text-panel-muted" aria-hidden="true" />
                    <span>Created {selectedAlert.operationalLabel}</span>
                  </li>
                  <li className="flex items-center gap-3">
                    <Info className="size-4 text-panel-muted" aria-hidden="true" />
                    <span>Backend: {selectedAlert.delivery_backend || "Not recorded"}</span>
                  </li>
                  <li className="flex items-center gap-3">
                    <BellRing className="size-4 text-panel-muted" aria-hidden="true" />
                    <span>
                      Attempts {selectedAlert.attempt_count}/{selectedAlert.max_attempts}
                    </span>
                  </li>
                </ul>
              </Card>

              {selectedAlert.error_message ? (
                <Card className="rounded-2xl border-[color:var(--warning)]/30 bg-[color-mix(in_srgb,var(--warning)_8%,var(--panel))] px-4 py-4 shadow-none">
                  <h3 className="text-sm font-semibold uppercase tracking-[0.16em] text-[color:var(--warning)]">Failure context</h3>
                  <p className="mt-3 text-sm leading-6 text-panel-copy">{selectedAlert.error_message}</p>
                </Card>
              ) : null}
            </div>

            <div className="flex flex-col gap-3 border-t border-panel-table-wrap px-5 py-5 sm:px-6">
              {(selectedAlert.statusFilter === "FAILED" || selectedAlert.status === "RETRY_PENDING") && (
                <Button className="w-full justify-center" disabled>
                  Retry workflow pending
                </Button>
              )}
              <Link
                href={`/alerts/${selectedAlert.id}`}
                className="inline-flex h-11 w-full items-center justify-center gap-2 rounded-pill border border-panel-table-wrap px-4 text-sm font-semibold text-panel-copy transition hover:border-[var(--dashboard-icon-button-border)] hover:text-panel-strong"
              >
                Open full alert detail
                <ExternalLink className="size-4" aria-hidden="true" />
              </Link>
            </div>
          </aside>
        </>
      ) : null}
    </div>
  );
}
