"use client";

import {
  AlertTriangle,
  BellRing,
  Clock3,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  CircleAlert,
  CloudRain,
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
import { fetchAlertsDataViaBff, type AlertRecord } from "@/lib/dashboard";
import { describeFreshness, formatRelativeTimestamp, getLatestTimestamp } from "@/lib/freshness";

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

export default function AlertsPage() {
  const { currentUser } = useAuth();
  const [alerts, setAlerts] = useState<AlertRecord[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [selectedType, setSelectedType] = useState<AlertTypeFilter>("ALL");
  const [selectedStatus, setSelectedStatus] = useState<AlertStatusFilter>("ALL");
  const [page, setPage] = useState(1);
  const [refreshKey, setRefreshKey] = useState(0);
  const [selectedAlertId, setSelectedAlertId] = useState<number | null>(null);

  useEffect(() => {
    if (!currentUser) {
      return;
    }
    let isActive = true;

    async function loadAlerts() {
      setIsLoading(true);
      setError(null);

      try {
        const response = await fetchAlertsDataViaBff();

        if (!isActive) {
          return;
        }

        setAlerts(response.results);
      } catch (loadError) {
        if (!isActive) {
          return;
        }

        setError(loadError instanceof Error ? loadError.message : "Unable to load alerts.");
      } finally {
        if (isActive) {
          setIsLoading(false);
        }
      }
    }

    void loadAlerts();

    return () => {
      isActive = false;
    };
  }, [currentUser, refreshKey]);

  const decoratedAlerts = useMemo<DecoratedAlert[]>(
    () =>
      alerts.map((alert) => {
        const alertType = classifyAlertType(alert);
        const timestamp = alert.sent_at ?? alert.created_at;

        return {
          ...alert,
          alertType,
          statusFilter: getStatusFilter(alert.status),
          statusLabel: getStatusLabel(alert.status),
          channelLabel: getChannelLabel(alert.channel),
          timeLabel: formatSentTime(timestamp),
          relativeLabel: formatRelativeShort(timestamp),
          operationalLabel: formatRelativeTimestamp(timestamp),
          severity: getAlertSeverity(alert.risk_score),
          severityLabel: getSeverityLabel(getAlertSeverity(alert.risk_score)),
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
  const topbarTimestampLabel = isLoading ? "Refreshing..." : formatRelativeShort(latestAlertTimestamp);
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
    <div className="alerts-dashboard">
      <DashboardTopbar
        title="Alerts"
        subtitle="Operational alert coordination"
        lastUpdatedLabel={topbarTimestampLabel}
        lastUpdatedTone={alertFreshness.isStale ? "stale" : "default"}
        onRefresh={() => setRefreshKey((value) => value + 1)}
      />

      {error ? (
        <div className="status status-error">
          <AlertTriangle className="section-icon" aria-hidden="true" />
          {error}
        </div>
      ) : null}

      {!isLoading && !error && decoratedAlerts.length === 0 ? (
        <div className="status status-warning">
          <AlertTriangle className="section-icon" aria-hidden="true" />
          No alerts are available yet in your visible scope.
        </div>
      ) : null}

      {!isLoading && !error && decoratedAlerts.length > 0 && alertFreshness.isStale ? (
        <section className={`alerts-freshness-state alerts-freshness-state-${freshnessTone}`}>
          <div className="alerts-freshness-copy">
            <div className="alerts-freshness-title">
              <AlertTriangle aria-hidden="true" />
              <strong>
                {freshnessTone === "critical" ? "Data freshness issue" : "Freshness warning"} - last update{" "}
                {formatExactTimestamp(latestAlertTimestamp)} ({formatRelativeShort(latestAlertTimestamp)})
              </strong>
            </div>
            <p>Operators should verify ingestion health before treating these alert counts as current field conditions.</p>
          </div>

          <div className="alerts-freshness-actions">
            <button type="button" className="alerts-freshness-button" onClick={() => setRefreshKey((value) => value + 1)}>
              Refresh data
            </button>
            <Link href="/system" className="alerts-freshness-link">
              View pipeline status
            </Link>
          </div>
        </section>
      ) : null}

      <section className="alerts-hero">
        <div className="alerts-hero-copy">
          <h1>Alerts Monitoring</h1>
          <p>Track delivery status, operational risk activity, and ward-level alert pressure across Migori County.</p>
        </div>
      </section>

      <section className="alerts-metrics">
        <article className="alerts-metric-card alerts-metric-card-primary">
          <div className="alerts-metric-header">
            <span>Alerts sent (last 24 hours)</span>
            <ChevronRight aria-hidden="true" />
          </div>
          <strong>{isLoading ? "..." : alertsLast24Hours.toLocaleString()}</strong>
          <p>
            {isLoading
              ? "Checking recent delivery volume"
              : `${sentTrend >= 0 ? "+" : ""}${sentTrend} vs previous 24h`}
          </p>
        </article>

        <article className="alerts-metric-card alerts-metric-card-amber alerts-metric-card-urgent">
          <div className="alerts-metric-header">
            <span>Active alerts</span>
            <BellRing aria-hidden="true" />
          </div>
          <strong>{isLoading ? "..." : activeAlertsCount}</strong>
          <p>Ongoing risk monitoring cycles still awaiting a clean resolution path.</p>
        </article>

        <article
          className={`alerts-metric-card ${
            failedCount > 0 ? "alerts-metric-card-danger" : "alerts-metric-card-healthy"
          }`}
        >
          <div className="alerts-metric-header">
            <span>Delivery failures</span>
            <AlertTriangle aria-hidden="true" />
          </div>
          <strong>{isLoading ? "..." : failedCount}</strong>
          <p>{lastFailure ? `Last failure ${formatRelativeShort(lastFailure.created_at)}` : "Delivery reliability currently stable."}</p>
        </article>
      </section>

      <section className="alerts-table-panel">
        <div className="alerts-toolbar">
          <div className="alerts-toolbar-group">
            <label className="alerts-search-field alerts-search-field-toolbar">
              <Search aria-hidden="true" />
              <input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search ward, alert type, or channel..."
              />
            </label>

            <label className="alerts-select-field">
              <span>Alert type</span>
              <select value={selectedType} onChange={(event) => setSelectedType(event.target.value as AlertTypeFilter)}>
                {ALERT_TYPE_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
              <ChevronDown aria-hidden="true" />
            </label>

            <div className="alerts-status-tabs" role="tablist" aria-label="Alert status filters">
              {STATUS_FILTER_OPTIONS.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  className={option.value === selectedStatus ? "is-active" : ""}
                  onClick={() => setSelectedStatus(option.value)}
                >
                  {option.label}
                </button>
              ))}
            </div>
          </div>

          <button
            type="button"
            className="alerts-export-button"
            onClick={() => downloadAlertsCsv(filteredAlerts)}
            disabled={!filteredAlerts.length}
          >
            <Download aria-hidden="true" />
            <span>Export CSV</span>
          </button>
        </div>

        <div className="alerts-table-wrap">
          <table className="alerts-table">
            <thead>
              <tr>
                <th>Alert type</th>
                <th>Administrative ward</th>
                <th>Channel</th>
                <th>Status</th>
                <th>Sent time</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                Array.from({ length: ROWS_PER_PAGE }).map((_, index) => (
                  <tr key={`alerts-skeleton-${index}`} className="alerts-row-skeleton">
                    <td colSpan={6}>
                      <div className="alerts-skeleton-line alerts-skeleton-line-wide" />
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
                      className="alerts-table-row"
                      onClick={() => setSelectedAlertId(alert.id)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" || event.key === " ") {
                          event.preventDefault();
                          setSelectedAlertId(alert.id);
                        }
                      }}
                      tabIndex={0}
                    >
                      <td>
                        <div className="alerts-type-cell">
                          <span className={`alerts-type-icon alerts-tone-${alert.alertType.tone}`}>
                            <AlertIcon aria-hidden="true" />
                          </span>
                          <div className="alerts-type-copy">
                            <strong>{alert.alertType.label}</strong>
                            <div className="alerts-type-meta">
                              <span className="alerts-auto-pill">Auto-triggered</span>
                              <span className={`alerts-severity-pill alerts-severity-${alert.severity.toLowerCase()}`}>
                                <span className="alerts-severity-dot" aria-hidden="true" />
                                {alert.severityLabel}
                              </span>
                            </div>
                          </div>
                        </div>
                      </td>
                      <td className="alerts-ward-cell">
                        <strong>{alert.ward_name}</strong>
                      </td>
                      <td>
                        <div className="alerts-channel-cell">
                          <ChannelIcon aria-hidden="true" />
                          <span>{alert.channelLabel}</span>
                        </div>
                      </td>
                      <td>
                        <div className="alerts-status-stack">
                          <span
                            className={`dashboard-status-badge ${
                              alert.statusFilter === "SENT"
                                ? "dashboard-badge-success"
                                : alert.statusFilter === "FAILED"
                                  ? "dashboard-badge-danger"
                                  : "dashboard-badge-warning"
                            }`}
                              >
                            {alert.statusLabel}
                          </span>
                          {alert.status === "RETRY_PENDING" ? (
                            <span className="alerts-retry-label">Retry queue active</span>
                          ) : null}
                        </div>
                      </td>
                      <td className="alerts-time-cell">{alert.timeLabel}</td>
                      <td>
                        <button
                          type="button"
                          className="alerts-row-action"
                          onClick={(event) => {
                            event.stopPropagation();
                            setSelectedAlertId(alert.id);
                          }}
                        >
                          {alert.statusFilter === "FAILED" || alert.status === "RETRY_PENDING" ? "Retry review" : "Open"}
                        </button>
                      </td>
                    </tr>
                  );
                })
              ) : (
                <tr>
                  <td colSpan={6} className="alerts-table-empty">
                    No alerts match the current search and filter combination.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <div className="alerts-table-footer">
          <div className="alerts-table-meta">
            <span>
              {Math.min(filteredAlerts.length, safePage * ROWS_PER_PAGE)} of {filteredAlerts.length} alerts
            </span>
            <span className="alerts-confidence-pill">Reliable for escalation decisions</span>
          </div>

          {totalPages > 1 ? (
            <div className="alerts-pagination">
              <button type="button" onClick={() => setPage((value) => Math.max(1, value - 1))} disabled={safePage === 1}>
                <ChevronLeft aria-hidden="true" />
              </button>
              {paginationItems.map((item, index) =>
                item === "..." ? (
                  <span key={`ellipsis-${index}`} className="alerts-pagination-ellipsis">
                    ...
                  </span>
                ) : (
                  <button
                    key={item}
                    type="button"
                    className={item === safePage ? "is-active" : ""}
                    onClick={() => setPage(item)}
                  >
                    {item}
                  </button>
                ),
              )}
              <button
                type="button"
                onClick={() => setPage((value) => Math.min(totalPages, value + 1))}
                disabled={safePage === totalPages}
              >
                <ChevronRight aria-hidden="true" />
              </button>
            </div>
          ) : null}
        </div>
      </section>

      <section className="alerts-lower-grid">
        <article className="alerts-map-card">
          <div className="alerts-section-heading">
            <div>
              <h2>Active Alert Zones</h2>
              <p>Real-time operational hotspots based on visible ward alert pressure.</p>
            </div>

            <div className="alerts-map-tabs">
              <button type="button" className="is-active">
                Satellite
              </button>
              <button type="button">Topographic</button>
            </div>
          </div>

          <div className="alerts-map-visual">
            <div className="alerts-map-overlay-card">
              <span>Critical zone</span>
              <strong>{activeZones[0]?.wardName ?? "No active ward"}</strong>
              <p>{activeZones[0] ? `${activeZones[0].count} visible alerts in current scope` : "Awaiting live alert activity"}</p>
            </div>

            <div className="alerts-map-grid">
              {activeZones.length > 0
                ? activeZones.map((zone, index) => (
                    <div
                      key={zone.wardName}
                      className={`alerts-map-node ${index === 0 ? "is-primary" : ""}`}
                      style={{
                        left: `${20 + index * 18}%`,
                        top: `${18 + (index % 3) * 19}%`,
                      }}
                    >
                      <span>{zone.wardName}</span>
                    </div>
                  ))
                : null}
            </div>
          </div>
        </article>

        <aside className="alerts-aside">
          <article className="alerts-protocol-card">
            <div className="alerts-section-heading alerts-section-heading-compact">
              <div>
                <h2>Response Protocol</h2>
                <p>Immediate field coordination guidance for the highest-pressure visible ward.</p>
              </div>
            </div>

            <strong>
              {mostCriticalAlert
                ? `${mostCriticalAlert.severity === "HIGH" ? "Escalation Required" : "Escalation Review"} - ${mostCriticalAlert.ward_name}`
                : "No active escalation required."}
            </strong>
            <p>
              {mostCriticalAlert
                ? `Priority signal: ${mostCriticalAlert.alertType.label} via ${mostCriticalAlert.channelLabel.toLowerCase()} triggered ${mostCriticalAlert.relativeLabel}.`
                : "Visible alerts are currently within a stable operating window."}
            </p>
            {mostCriticalAlert ? (
              <Link href={`/alerts/${mostCriticalAlert.id}`} className="alerts-protocol-link">
                Start Escalation Protocol
                <ChevronRight aria-hidden="true" />
              </Link>
            ) : null}
          </article>

          <article className="alerts-signal-card">
            <span className="alerts-signal-label">Intelligence signal</span>
            <strong>
              {mostCriticalAlert ? `${Math.max(72, Math.round((mostCriticalAlert.risk_score ?? 0) * 0.9))}% alert trigger probability` : "No high-confidence alert signal"}
            </strong>
            <p>{alertFreshness.isStale ? "Data quality: review freshness" : "Data quality: good"}</p>
          </article>
        </aside>
      </section>

      {selectedAlert ? (
        <div
          className="alerts-drawer-backdrop"
          onClick={() => setSelectedAlertId(null)}
          aria-hidden="true"
        />
      ) : null}

      {selectedAlert ? (
        <aside className="alerts-drawer" aria-label="Alert detail drawer">
          <div className="alerts-drawer-header">
            <div>
              <span className="alerts-drawer-kicker">Alert detail</span>
              <h2>{selectedAlert.alertType.label}</h2>
              <p>{selectedAlert.ward_name}</p>
            </div>

            <button type="button" className="alerts-drawer-close" onClick={() => setSelectedAlertId(null)} aria-label="Close alert detail">
              <X aria-hidden="true" />
            </button>
          </div>

          <div className="alerts-drawer-grid">
            <div className="alerts-drawer-stat">
              <span>Status</span>
              <strong>{selectedAlert.statusLabel}</strong>
            </div>
            <div className="alerts-drawer-stat">
              <span>Severity</span>
              <strong>{selectedAlert.severityLabel}</strong>
            </div>
            <div className="alerts-drawer-stat">
              <span>Channel</span>
              <strong>{selectedAlert.channelLabel}</strong>
            </div>
            <div className="alerts-drawer-stat">
              <span>Sent time</span>
              <strong>{selectedAlert.timeLabel}</strong>
            </div>
          </div>

          <div className="alerts-drawer-section">
            <h3>Operational message</h3>
            <p>{selectedAlert.message}</p>
          </div>

          <div className="alerts-drawer-section">
            <h3>Delivery path</h3>
            <ul className="alerts-drawer-list">
              <li>
                <Clock3 aria-hidden="true" />
                <span>Created {selectedAlert.operationalLabel}</span>
              </li>
              <li>
                <Info aria-hidden="true" />
                <span>Backend: {selectedAlert.delivery_backend || "Not recorded"}</span>
              </li>
              <li>
                <BellRing aria-hidden="true" />
                <span>
                  Attempts {selectedAlert.attempt_count}/{selectedAlert.max_attempts}
                </span>
              </li>
            </ul>
          </div>

          {selectedAlert.error_message ? (
            <div className="alerts-drawer-section alerts-drawer-section-warning">
              <h3>Failure context</h3>
              <p>{selectedAlert.error_message}</p>
            </div>
          ) : null}

          <div className="alerts-drawer-actions">
            {(selectedAlert.statusFilter === "FAILED" || selectedAlert.status === "RETRY_PENDING") && (
              <button type="button" className="alerts-drawer-action alerts-drawer-action-primary">
                Retry workflow review
              </button>
            )}
            <Link href={`/alerts/${selectedAlert.id}`} className="alerts-drawer-action alerts-drawer-action-secondary">
              Open full alert detail
              <ExternalLink aria-hidden="true" />
            </Link>
          </div>
        </aside>
      ) : null}
    </div>
  );
}
