"use client";

import {
  AlertTriangle,
  BellRing,
  ChevronLeft,
  ChevronRight,
  CloudRain,
  Clock3,
  Download,
  ExternalLink,
  Info,
  Search,
  Smartphone,
  X,
} from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
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
import {
  createSensitiveExportViaBff,
  downloadSensitiveExportFile,
  downloadSensitiveExportViaBff,
  type AlertRecord,
} from "@/lib/dashboard";
import { describeFreshness, formatRelativeTimestamp, getLatestTimestamp } from "@/lib/freshness";
import { hasActionCapability } from "@/lib/capabilities";
import { canExportSensitiveReports } from "@/lib/roles";
import { useAlertsQuery } from "@/queries/use-alerts-query";
import { useCreateChvCoverageRequestFromAlertMutation } from "@/queries/use-create-chv-coverage-request-from-alert-mutation";
import { useCreateChvCoverageRequestMutation } from "@/queries/use-create-chv-coverage-request-mutation";
import { useLiveChvCoverageRequestForWardQuery } from "@/queries/use-live-chv-coverage-request-for-ward-query";

type AlertStatusFilter = "ALL" | "SENT" | "PENDING" | "FAILED";

type DecoratedAlert = AlertRecord & {
  statusFilter: Exclude<AlertStatusFilter, "ALL">;
  statusLabel: string;
  channelLabel: string;
  timeLabel: string;
  relativeLabel: string;
  createdRelativeLabel: string;
};

const STATUS_FILTER_OPTIONS: Array<{ value: AlertStatusFilter; label: string }> = [
  { value: "ALL", label: "All" },
  { value: "SENT", label: "Sent" },
  { value: "PENDING", label: "Pending" },
  { value: "FAILED", label: "Failed" },
];

const ROWS_PER_PAGE = 5;

function alertIconSurface(tone: "brand" | "warning" | "danger" | "success") {
  switch (tone) {
    case "warning":
      return "border-[color-mix(in_srgb,var(--warning)_30%,var(--dashboard-panel-border))] bg-[color-mix(in_srgb,var(--warning)_14%,var(--dashboard-panel-surface))] text-[color:var(--warning)]";
    case "danger":
      return "border-[color-mix(in_srgb,var(--danger)_28%,var(--dashboard-panel-border))] bg-[color-mix(in_srgb,var(--danger)_13%,var(--dashboard-panel-surface))] text-[color:var(--danger)]";
    case "success":
      return "border-[color-mix(in_srgb,var(--success)_26%,var(--dashboard-panel-border))] bg-[color-mix(in_srgb,var(--success)_13%,var(--dashboard-panel-surface))] text-[color:var(--success)]";
    case "brand":
    default:
      return "border-[color-mix(in_srgb,var(--brand)_24%,var(--dashboard-panel-border))] bg-[color-mix(in_srgb,var(--brand)_13%,var(--dashboard-panel-surface))] text-brand";
  }
}

function isAlertActionable(alert: AlertRecord | DecoratedAlert) {
  return alert.status === "FAILED" || alert.status === "RETRY_PENDING";
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
      return "SMS";
    case "WHATSAPP":
      return "WhatsApp";
    case "DASHBOARD":
    default:
      return "Dashboard";
  }
}

function getChannelIcon(channel: AlertRecord["channel"]) {
  switch (channel) {
    case "SMS":
      return Smartphone;
    case "DASHBOARD":
    default:
      return CloudRain;
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

function formatAlertPublicId(alertId: number) {
  return `AL-${String(alertId).padStart(4, "0")}`;
}

function getAlertPriorityRank(alert: AlertRecord | DecoratedAlert) {
  if (alert.status === "FAILED") return 4;
  if (alert.status === "RETRY_PENDING") return 3;
  if (alert.status === "QUEUED") return 2;
  return 1;
}

function getAttentionReason(alert: DecoratedAlert) {
  if (alert.status === "FAILED") {
    return "Delivery failure requires operator review before the alert is treated as completed.";
  }
  if (alert.status === "RETRY_PENDING") {
    return "Retry pending in the backend still needs review to confirm whether delivery follow-up is required.";
  }
  if (alert.status === "QUEUED") {
    return "Alert is still queued in the visible delivery state feed.";
  }
  return "No immediate delivery concern is visible for this alert record.";
}

function getRecommendedAlertAction(alert: DecoratedAlert) {
  return isAlertActionable(alert) ? "Open review" : "Open alert record";
}

function getOperatorActionLabel(alert: DecoratedAlert) {
  if (alert.status === "FAILED") return "Needs escalation";
  if (alert.status === "RETRY_PENDING") return "Needs review";
  return "No action";
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

export default function AlertsPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { currentUser } = useAuth();
  const [search, setSearch] = useState("");
  const [selectedStatus, setSelectedStatus] = useState<AlertStatusFilter>("ALL");
  const [page, setPage] = useState(1);
  const [selectedAlertId, setSelectedAlertId] = useState<number | null>(null);
  const [coverageRequestFeedback, setCoverageRequestFeedback] = useState<string | null>(null);
  const [exportFeedback, setExportFeedback] = useState<string | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);
  const [isExporting, setIsExporting] = useState(false);
  const alertsQuery = useAlertsQuery({ enabled: Boolean(currentUser) });
  const createFromAlertMutation = useCreateChvCoverageRequestFromAlertMutation();
  const createCoverageRequestMutation = useCreateChvCoverageRequestMutation();
  const alerts = useMemo(() => alertsQuery.data ?? [], [alertsQuery.data]);
  const isLoading = alertsQuery.isPending;
  const isRefreshing = alertsQuery.isFetching;
  const error = alertsQuery.error instanceof Error ? alertsQuery.error.message : null;

  const decoratedAlerts = useMemo<DecoratedAlert[]>(
    () =>
      alerts.map((alert) => {
        const timestamp = alert.sent_at ?? alert.created_at;

        return {
          ...alert,
          statusFilter: getStatusFilter(alert.status),
          statusLabel: getStatusLabel(alert.status),
          channelLabel: getChannelLabel(alert.channel),
          timeLabel: formatSentTime(timestamp),
          relativeLabel: formatRelativeShort(timestamp),
          createdRelativeLabel: formatRelativeTimestamp(timestamp),
        };
      }),
    [alerts],
  );
  const wardFilterFromQuery = useMemo(() => {
    const rawWardId = searchParams.get("ward_id");
    if (!rawWardId) {
      return null;
    }

    const parsedWardId = Number(rawWardId);
    return Number.isFinite(parsedWardId) ? parsedWardId : null;
  }, [searchParams]);

  const prioritizedAlerts = useMemo(
    () =>
      [...decoratedAlerts].sort((left, right) => {
        const priorityDiff = getAlertPriorityRank(right) - getAlertPriorityRank(left);
        if (priorityDiff !== 0) {
          return priorityDiff;
        }

        const riskDiff = (right.risk_score ?? 0) - (left.risk_score ?? 0);
        if (riskDiff !== 0) {
          return riskDiff;
        }

        return new Date(right.created_at).getTime() - new Date(left.created_at).getTime();
      }),
    [decoratedAlerts],
  );

  const filteredAlerts = useMemo(() => {
    const normalizedSearch = search.trim().toLowerCase();

    return prioritizedAlerts.filter((alert) => {
      if (wardFilterFromQuery !== null && alert.ward !== wardFilterFromQuery) {
        return false;
      }

      if (selectedStatus !== "ALL" && alert.statusFilter !== selectedStatus) {
        return false;
      }

      if (!normalizedSearch) {
        return true;
      }

      return (
        formatAlertPublicId(alert.id).toLowerCase().includes(normalizedSearch) ||
        alert.ward_name.toLowerCase().includes(normalizedSearch) ||
        alert.message.toLowerCase().includes(normalizedSearch) ||
        alert.channelLabel.toLowerCase().includes(normalizedSearch) ||
        alert.recipient.toLowerCase().includes(normalizedSearch)
      );
    });
  }, [prioritizedAlerts, search, selectedStatus, wardFilterFromQuery]);

  useEffect(() => {
    setPage(1);
  }, [search, selectedStatus]);

  const requiresAttentionAlerts = useMemo(
    () => prioritizedAlerts.filter((alert) => isAlertActionable(alert)),
    [prioritizedAlerts],
  );
  const requiresAttentionCount = useMemo(
    () => requiresAttentionAlerts.length,
    [requiresAttentionAlerts],
  );
  const retryPendingCount = useMemo(
    () => decoratedAlerts.filter((alert) => alert.status === "RETRY_PENDING").length,
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

  const mostCriticalAlert = prioritizedAlerts[0] ?? null;

  const selectedAlert = useMemo(
    () => decoratedAlerts.find((alert) => alert.id === selectedAlertId) ?? null,
    [decoratedAlerts, selectedAlertId],
  );
  const canRequestCoverage = hasActionCapability(currentUser, "manage_chv_operations");
  const canExportCsv = canExportSensitiveReports(currentUser);
  const isCoverageRequestPending = createFromAlertMutation.isPending || createCoverageRequestMutation.isPending;
  const liveCoverageRequestQuery = useLiveChvCoverageRequestForWardQuery({
    wardId: selectedAlert?.ward ?? null,
    enabled: Boolean(currentUser) && Boolean(selectedAlert?.ward),
  });
  const liveCoverageRequest = liveCoverageRequestQuery.data ?? null;
  const coverageRequestActionLabel = liveCoverageRequest
    ? "View CHV coverage request"
    : "Request CHV coverage";
  const coverageRequestPendingLabel = liveCoverageRequest
    ? "Opening CHV coverage request..."
    : "Preparing CHV coverage request...";

  async function handleAlertsCsvExport() {
    setExportFeedback(null);
    setExportError(null);
    setIsExporting(true);

    try {
      const exportRequest = await createSensitiveExportViaBff({
        export_type: "ALERT_LIST_CSV",
        purpose: "Operator requested alert monitoring CSV for delivery review.",
        filters: { alert_ids: filteredAlerts.map((alert) => alert.id) },
      });

      if (exportRequest.approval_state !== "APPROVED") {
        setExportFeedback("Sensitive export request is pending admin approval.");
        return;
      }

      const download = await downloadSensitiveExportViaBff(exportRequest.public_id);
      downloadSensitiveExportFile(download);
      setExportFeedback("Sensitive export downloaded and audited.");
    } catch (error) {
      setExportError(error instanceof Error ? error.message : "Unable to request sensitive export.");
    } finally {
      setIsExporting(false);
    }
  }

  const freshnessAgeMinutes = latestAlertTimestamp
    ? Math.max(0, Math.round((Date.now() - new Date(latestAlertTimestamp).getTime()) / 60000))
    : Number.POSITIVE_INFINITY;
  const freshnessTone = freshnessAgeMinutes >= 6 * 60 ? "critical" : freshnessAgeMinutes >= 20 ? "warning" : "healthy";

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
      {createFromAlertMutation.error instanceof Error ? (
        <StatusBanner tone="danger" icon={<AlertTriangle aria-hidden="true" />}>
          {createFromAlertMutation.error.message}
        </StatusBanner>
      ) : null}
      {createCoverageRequestMutation.error instanceof Error ? (
        <StatusBanner tone="danger" icon={<AlertTriangle aria-hidden="true" />}>
          {createCoverageRequestMutation.error.message}
        </StatusBanner>
      ) : null}
      {exportError ? (
        <StatusBanner tone="danger" icon={<AlertTriangle aria-hidden="true" />}>
          {exportError}
        </StatusBanner>
      ) : null}
      {coverageRequestFeedback ? <StatusBanner tone="success">{coverageRequestFeedback}</StatusBanner> : null}
      {exportFeedback ? <StatusBanner tone="info">{exportFeedback}</StatusBanner> : null}

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
                  "mt-0.5 inline-flex size-9 shrink-0 items-center justify-center rounded-full border",
                  alertIconSurface(freshnessTone === "critical" ? "danger" : "warning"),
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
                  Operators should verify ingestion health before treating these alert counts as recent field
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
          title="Alerts Coordination"
          description="Review alert records that need attention first, then scan the wider visible delivery queue."
        />

        <div className="grid gap-4 md:grid-cols-3">
            <Card className="rounded-3xl bg-panel px-5 py-5">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.18em] text-panel-subtle">Requires attention</p>
                  <div className="mt-3 text-4xl font-semibold leading-none text-panel-strong">
                    {isLoading ? "..." : requiresAttentionCount.toLocaleString()}
                  </div>
                </div>
                <span className={cn("inline-flex size-10 items-center justify-center rounded-full border", alertIconSurface("brand"))}>
                  <ChevronRight className="size-4" aria-hidden="true" />
                </span>
              </div>
              <p className="mt-4 text-sm text-panel-muted">
                {isLoading ? "Checking attention queue" : "Retry-pending and failed alerts that still need review."}
              </p>
            </Card>

            <Card className="rounded-3xl border-[color:var(--warning)]/20 bg-panel px-5 py-5">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.18em] text-panel-subtle">Delivered successfully</p>
                  <div className="mt-3 text-4xl font-semibold leading-none text-panel-strong">
                    {isLoading ? "..." : decoratedAlerts.filter((alert) => alert.status === "DELIVERED").length}
                  </div>
                </div>
                <span className={cn("inline-flex size-10 items-center justify-center rounded-full border", alertIconSurface("warning"))}>
                  <BellRing className="size-4" aria-hidden="true" />
                </span>
              </div>
              <p className="mt-4 text-sm text-panel-muted">
                Alert records already delivered in the visible scope.
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
                    "inline-flex size-10 items-center justify-center rounded-full border",
                    alertIconSurface(failedCount > 0 ? "danger" : "success"),
                  )}
                >
                  <AlertTriangle className="size-4" aria-hidden="true" />
                </span>
              </div>
              <p className="mt-4 text-sm text-panel-muted">
                {failedCount > 0
                  ? "Failed alerts remain in the queue and should be reviewed first."
                  : "No visible delivery failures in scope."}
              </p>
            </Card>
        </div>
      </section>

      <section className="grid gap-5 xl:grid-cols-[minmax(0,1.75fr)_minmax(18rem,0.85fr)] xl:items-start">
        <div className="space-y-4">
          <Card className="rounded-[2rem] bg-panel px-5 py-5 sm:px-6">
            <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
              <div className="flex min-w-0 flex-1 flex-col gap-4 lg:flex-row lg:flex-wrap lg:items-end">
                <InputShell
                  className="min-w-0 flex-[1.4]"
                  icon={<Search className="size-4" aria-hidden="true" />}
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder="Search alert ID, ward, recipient, or channel..."
                />

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

              {canExportCsv ? (
                <Button
                  variant="secondary"
                  className="h-11 self-start bg-[var(--dashboard-icon-button-surface)] px-4 xl:self-end"
                  onClick={() => {
                    void handleAlertsCsvExport();
                  }}
                  disabled={!filteredAlerts.length || isExporting}
                >
                  <Download className="size-4" aria-hidden="true" />
                  <span>{isExporting ? "Requesting Export" : "Export CSV"}</span>
                </Button>
              ) : null}
            </div>

            <div className="mt-4 overflow-hidden rounded-[1.5rem] border border-panel-table-wrap">
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-panel-table-wrap text-sm">
                  <thead className="bg-[color-mix(in_srgb,var(--dashboard-table-line)_30%,transparent)]">
                    <tr className="text-left">
                      {["Alert record", "Administrative ward", "Channel", "Status", "Sent time", "Action"].map(
                        (label) => (
                          <th
                            key={label}
                            className="px-5 py-4 text-[0.72rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle"
                          >
                            {label}
                          </th>
                        ),
                      )}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-panel-table-wrap bg-panel">
                    {isLoading ? (
                      Array.from({ length: ROWS_PER_PAGE }).map((_, index) => (
                        <tr key={`alerts-skeleton-${index}`}>
                          <td colSpan={6} className="px-5 py-4">
                            <div className="h-6 w-full animate-pulse rounded-full bg-[color-mix(in_srgb,var(--dashboard-table-line)_55%,transparent)]" />
                          </td>
                        </tr>
                      ))
                    ) : visibleAlerts.length > 0 ? (
                      visibleAlerts.map((alert) => {
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
                            <td className="px-5 py-3.5 align-top">
                              <div className="min-w-0">
                                <div className="flex items-center gap-2">
                                  {isAlertActionable(alert) ? (
                                    <span
                                      className={cn(
                                        "inline-flex size-2 rounded-full",
                                        alert.status === "FAILED"
                                          ? "bg-[color:var(--danger)]"
                                          : "bg-[color:var(--warning)]",
                                      )}
                                      aria-hidden="true"
                                    />
                                  ) : null}
                                  <div className="font-semibold text-panel-strong">
                                    {formatAlertPublicId(alert.id)}
                                  </div>
                                </div>
                              </div>
                            </td>
                            <td className="px-5 py-3.5 align-top font-semibold text-panel-strong">
                              {alert.ward_name}
                            </td>
                            <td className="px-5 py-3.5 align-top">
                              <div className="flex items-center gap-2 text-panel-copy">
                                <ChannelIcon className="size-4 text-panel-muted" aria-hidden="true" />
                                <span>{alert.channelLabel}</span>
                              </div>
                            </td>
                            <td className="px-5 py-3.5 align-top">
                              <div className="space-y-1.5">
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
                                  <p className="text-xs font-medium text-[color:var(--warning)]">Needs review</p>
                                ) : alert.status === "FAILED" ? (
                                  <p className="text-xs font-medium text-[color:var(--danger)]">Needs escalation</p>
                                ) : null}
                              </div>
                            </td>
                            <td className="px-5 py-3.5 align-top text-panel-copy">{alert.timeLabel}</td>
                            <td className="px-5 py-3.5 align-top">
                              <Button
                                variant="ghost"
                                className="h-9 rounded-pill px-3 text-sm"
                                onClick={(event) => {
                                  event.stopPropagation();
                                  setSelectedAlertId(alert.id);
                                }}
                              >
                                {alert.statusFilter === "FAILED" || alert.status === "RETRY_PENDING"
                                  ? "Open review"
                                  : "Open"}
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
                <span>Showing all alerts (most require no action).</span>
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
        </div>

        <aside className="space-y-5">
          {requiresAttentionAlerts.length > 0 ? (
            <section className="space-y-4">
              <PageSectionHeader
                title="Requires attention"
                description="Retry-pending and failed alerts that still need operator review."
              />

              <div className="space-y-4">
                {requiresAttentionAlerts.slice(0, 2).map((alert, index) => (
                  <Card
                    key={alert.id}
                    className={cn(
                      "rounded-[1.75rem] px-6 py-6",
                      alert.status === "FAILED"
                        ? "border-[color:var(--danger)]/20 bg-[color-mix(in_srgb,var(--danger)_6%,var(--panel))]"
                        : "border-[color:var(--warning)]/20 bg-[color-mix(in_srgb,var(--warning)_6%,var(--panel))]",
                    )}
                  >
                    <div className="space-y-4">
                      <div className="space-y-3">
                        <div className="flex items-center gap-2">
                          <span
                            className={cn(
                              "inline-flex size-2.5 rounded-full",
                              alert.status === "FAILED"
                                ? "bg-[color:var(--danger)]"
                                : "bg-[color:var(--warning)]",
                            )}
                            aria-hidden="true"
                          />
                          <StatusBadge
                            tone={alert.status === "FAILED" ? "danger" : "warning"}
                            className="tracking-[0.12em]"
                          >
                            {index === 0 ? "Start here" : getOperatorActionLabel(alert)}
                          </StatusBadge>
                        </div>
                        <div className="space-y-1">
                          <strong className="block text-lg text-panel-strong">
                            {formatAlertPublicId(alert.id)} - {alert.ward_name}
                          </strong>
                          <p className="text-sm font-medium text-panel-copy">
                            {alert.statusLabel} ({alert.relativeLabel})
                          </p>
                        </div>
                        <p className="text-sm leading-6 text-panel-copy">{getAttentionReason(alert)}</p>
                      </div>

                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <div className="text-sm text-panel-muted">
                          {getOperatorActionLabel(alert)} - {alert.channelLabel}
                        </div>
                        <Button
                          variant="ghost"
                          className="h-10 rounded-pill px-4 text-sm"
                          onClick={() => setSelectedAlertId(alert.id)}
                        >
                          Open review
                        </Button>
                      </div>
                    </div>
                  </Card>
                ))}
              </div>
            </section>
          ) : null}

          <Card className="rounded-[2rem] bg-[linear-gradient(180deg,color-mix(in_srgb,var(--brand)_10%,var(--panel)),var(--panel))] px-5 py-5 lg:sticky lg:top-6">
            <span className="text-xs font-semibold uppercase tracking-[0.18em] text-panel-subtle">Queue status</span>
            <strong className="mt-3 block text-2xl leading-tight text-panel-strong">
              {requiresAttentionCount > 0
                ? `${requiresAttentionCount} alert${requiresAttentionCount === 1 ? "" : "s"} still need review`
                : "No alert review queue right now"}
            </strong>
            <p className="mt-3 text-sm text-panel-muted">
              {requiresAttentionCount > 0
                ? `${retryPendingCount} retry pending and ${failedCount} failed in the visible queue.`
                : alertFreshness.isStale
                  ? "Check feed freshness before treating this panel as recent."
                  : "Visible alerts do not currently require operator review."}
            </p>
          </Card>
        </aside>
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
                <h2 className="mt-2 text-2xl font-semibold text-panel-strong">{formatAlertPublicId(selectedAlert.id)}</h2>
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
                  ["Channel", selectedAlert.channelLabel],
                  ["Alert ID", formatAlertPublicId(selectedAlert.id)],
                  ["Sent time", selectedAlert.timeLabel],
                ].map(([label, value]) => (
                  <Card key={label} className="rounded-2xl px-4 py-4 shadow-none">
                    <span className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-subtle">{label}</span>
                    <strong className="mt-2 block text-base text-panel-strong">{value}</strong>
                  </Card>
                ))}
              </div>

              <Card className="rounded-2xl px-4 py-4 shadow-none">
                <h3 className="text-sm font-semibold uppercase tracking-[0.16em] text-panel-subtle">Alert message</h3>
                <p className="mt-3 text-sm leading-6 text-panel-copy">{selectedAlert.message}</p>
              </Card>

              <Card className="rounded-2xl px-4 py-4 shadow-none">
                <h3 className="text-sm font-semibold uppercase tracking-[0.16em] text-panel-subtle">Delivery path</h3>
                <ul className="mt-4 space-y-3 text-sm text-panel-copy">
                  <li className="flex items-center gap-3">
                    <Clock3 className="size-4 text-panel-muted" aria-hidden="true" />
                    <span>Created {selectedAlert.createdRelativeLabel}</span>
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

              {canRequestCoverage ? (
                <Card className="rounded-2xl px-4 py-4 shadow-none">
                  <h3 className="text-sm font-semibold uppercase tracking-[0.16em] text-panel-subtle">CHV coverage workflow</h3>
                  <p className="mt-3 text-sm leading-6 text-panel-copy">
                    {liveCoverageRequest
                      ? "A live CHV coverage request already exists for this ward, so this alert should open that request instead of starting a duplicate workflow."
                      : "Request CHV coverage only through the real alert-linked workflow. If a live request already exists for this ward, this handoff will route to that request instead of creating a duplicate."}
                  </p>
                </Card>
              ) : null}
            </div>

            <div className="flex flex-col gap-3 border-t border-panel-table-wrap px-5 py-5 sm:px-6">
              {canRequestCoverage ? (
                <Button
                  className="w-full justify-center"
                  disabled={isCoverageRequestPending}
                  onClick={async () => {
                    setCoverageRequestFeedback(null);

                    if (liveCoverageRequest) {
                      setSelectedAlertId(null);
                      router.push(`/chvs/requests/${liveCoverageRequest.public_id}`);
                      return;
                    }

                    if (!selectedAlert?.public_id) {
                      return;
                    }

                    try {
                      const handoff = await createFromAlertMutation.mutateAsync({
                        alert_public_ids: [selectedAlert.public_id],
                      });

                      if (handoff.mode === "EXISTING_LIVE_REQUEST" && handoff.existing_request) {
                        setCoverageRequestFeedback("A live CHV coverage request already exists for this ward.");
                        setSelectedAlertId(null);
                        router.push(`/chvs/requests/${handoff.existing_request.public_id}`);
                        return;
                      }

                      if (!handoff.create_defaults) {
                        throw new Error("Alert-linked request defaults were not returned.");
                      }

                      const createdRequest = await createCoverageRequestMutation.mutateAsync({
                        ward_id: handoff.create_defaults.ward_id,
                        priority: handoff.create_defaults.priority,
                        reason: handoff.create_defaults.reason,
                        requested_chv_count: handoff.create_defaults.requested_chv_count,
                        notes: handoff.create_defaults.notes,
                        trigger_source: handoff.create_defaults.trigger_source,
                        linked_alert_public_ids: handoff.create_defaults.linked_alert_public_ids,
                      });

                      setCoverageRequestFeedback("Alert-linked CHV coverage request created.");
                      setSelectedAlertId(null);
                      router.push(`/chvs/requests/${createdRequest.public_id}`);
                    } catch {
                      // Error banners already reflect the failing mutation.
                    }
                  }}
                >
                  {isCoverageRequestPending ? coverageRequestPendingLabel : coverageRequestActionLabel}
                </Button>
              ) : null}
              {(selectedAlert.statusFilter === "FAILED" || selectedAlert.status === "RETRY_PENDING") && (
                <Button className="w-full justify-center" disabled>
                  Retry unavailable
                </Button>
              )}
              <Link
                href={`/alerts/${selectedAlert.id}`}
                className="inline-flex h-11 w-full items-center justify-center gap-2 rounded-pill border border-panel-table-wrap px-4 text-sm font-semibold text-panel-copy transition hover:border-[var(--dashboard-icon-button-border)] hover:text-panel-strong"
              >
                Open record page
                <ExternalLink className="size-4" aria-hidden="true" />
              </Link>
            </div>
          </aside>
        </>
      ) : null}
    </div>
  );
}
