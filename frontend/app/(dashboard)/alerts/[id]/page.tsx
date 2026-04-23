"use client";

import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  ChevronRight,
  ClipboardCheck,
  CircleAlert,
  CloudRain,
  Download,
  Droplets,
  Hospital,
  MessageSquareWarning,
  Radio,
  Share2,
  ShieldAlert,
  Siren,
  Smartphone,
  Waves,
  XCircle,
} from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { DashboardTopbar } from "@/components/dashboard-topbar";
import { fetchAlertByIdViaBff, type AlertRecord, type WardDetailSummary } from "@/lib/dashboard";
import { describeFreshness, getLatestTimestamp } from "@/lib/freshness";

type AlertTypeMeta = {
  label: string;
  icon: typeof Droplets;
  tone: "red" | "amber" | "orange" | "blue" | "slate";
  triggerSource: string;
};

type TimelineEntry = {
  id: string;
  title: string;
  description: string;
  timestamp: string | null;
  tone: "primary" | "progress" | "success" | "danger";
  meta?: string;
};

type StateItem = {
  label: string;
  tone: "success" | "warning" | "neutral";
};

const ALERT_TYPE_META: Record<string, AlertTypeMeta> = {
  CHOLERA_RISK: {
    label: "Cholera Risk",
    icon: Droplets,
    tone: "red",
    triggerSource: "Cholera threshold exceeded",
  },
  FLOOD_RISK: {
    label: "Flood Risk",
    icon: Waves,
    tone: "blue",
    triggerSource: "Flood proxy exceeded",
  },
  WATER_CONTAMINATION: {
    label: "Water Contamination",
    icon: CircleAlert,
    tone: "red",
    triggerSource: "Water safety signal elevated",
  },
  HEAVY_RAINFALL: {
    label: "Heavy Rainfall",
    icon: CloudRain,
    tone: "orange",
    triggerSource: "Rainfall threshold exceeded",
  },
  OPERATIONAL_ALERT: {
    label: "Operational Alert",
    icon: ShieldAlert,
    tone: "slate",
    triggerSource: "Operational monitoring threshold crossed",
  },
};

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

function getChannelLabel(channel: AlertRecord["channel"]) {
  switch (channel) {
    case "SMS":
      return "SMS Alert";
    case "WHATSAPP":
      return "Radio Broadcast";
    case "DASHBOARD":
    default:
      return "USSD Notification";
  }
}

function getChannelAudience(channel: AlertRecord["channel"]) {
  switch (channel) {
    case "SMS":
      return "CHVs & officials";
    case "WHATSAPP":
      return "Field broadcast";
    case "DASHBOARD":
    default:
      return "Dashboard viewers";
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

function getStatusLabel(status: AlertRecord["status"]) {
  switch (status) {
    case "DELIVERED":
      return "Alert Delivered Successfully";
    case "FAILED":
      return "Delivery Failed";
    case "RETRY_PENDING":
      return "Delivery Retry Pending";
    case "QUEUED":
    default:
      return "Queued for Dispatch";
  }
}

function getStatusTone(status: AlertRecord["status"]) {
  switch (status) {
    case "DELIVERED":
      return "success";
    case "FAILED":
      return "danger";
    case "RETRY_PENDING":
      return "warning";
    case "QUEUED":
    default:
      return "neutral";
  }
}

function formatTimeStamp(timestamp: string | null) {
  if (!timestamp) {
    return "No timestamp";
  }

  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) {
    return "Invalid timestamp";
  }

  return date.toLocaleString([], {
    hour: "numeric",
    minute: "2-digit",
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

function formatTimeOnly(timestamp: string | null) {
  if (!timestamp) {
    return "--:--";
  }

  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) {
    return "--:--";
  }

  return date.toLocaleTimeString([], {
    hour: "numeric",
    minute: "2-digit",
    second: "2-digit",
  });
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

function formatAlertPublicId(alertId: number) {
  return `AL-${String(alertId).padStart(4, "0")}`;
}

function estimateSuccessRate(alert: AlertRecord) {
  if (alert.status === "DELIVERED") {
    return 98;
  }
  if (alert.status === "RETRY_PENDING") {
    return 74;
  }
  if (alert.status === "QUEUED") {
    return 52;
  }
  return 18;
}

function estimateFailureCount(alert: AlertRecord) {
  if (alert.status === "FAILED") {
    return Math.max(1, alert.max_attempts);
  }
  if (alert.status === "RETRY_PENDING") {
    return Math.max(1, alert.attempt_count);
  }
  return 0;
}

function getRiskMeaning(score: number | null) {
  const value = score ?? 0;

  if (value >= 75) {
    return {
      level: "High Risk",
      trend: "Escalating",
      summary: "Threshold crossed and field coordination should accelerate.",
    };
  }

  if (value >= 40) {
    return {
      level: "Medium Risk",
      trend: "Monitoring",
      summary: "Watch closely and prepare ward follow-up if indicators rise again.",
    };
  }

  return {
    level: "Low Risk",
    trend: "Stable",
    summary: "Threshold not crossed. Maintain routine monitoring and ward surveillance.",
  };
}

function buildTimeline(alert: AlertRecord, triggerSource: string): TimelineEntry[] {
  const items: TimelineEntry[] = [
    {
      id: "generated",
      title: "Alert generated by ML model",
      description: `Risk prediction generated using ${triggerSource.toLowerCase()} data.`,
      timestamp: alert.created_at,
      tone: "primary",
      meta: alert.risk_score !== null ? `Risk score: ${Math.round(alert.risk_score)}/100` : undefined,
    },
  ];

  if (alert.last_attempted_at || alert.sent_at || alert.status === "QUEUED" || alert.status === "RETRY_PENDING") {
    items.push({
      id: "dispatch",
      title: `Dispatching to ${getChannelLabel(alert.channel).toLowerCase()}`,
      description: `Routing through ${alert.delivery_backend || "primary delivery backend"}.`,
      timestamp: alert.last_attempted_at ?? alert.sent_at ?? alert.created_at,
      tone: "progress",
    });
  }

  if (alert.status === "DELIVERED" || alert.sent_at) {
    items.push({
      id: "delivered",
      title: "Delivery receipts recorded",
      description:
        alert.status === "DELIVERED"
          ? "Backend confirms successful delivery across the visible dispatch path."
          : "Delivery receipts are partially visible for this alert.",
      timestamp: alert.sent_at ?? alert.last_attempted_at,
      tone: "success",
    });
  }

  if (alert.status === "FAILED" || alert.status === "RETRY_PENDING" || alert.error_message) {
    items.push({
      id: "failure",
      title: alert.status === "FAILED" ? "Delivery failures logged" : "Retry workflow still active",
      description:
        alert.error_message ||
        (alert.status === "FAILED"
          ? "Delivery pipeline reported failures on the current dispatch path."
          : "The pipeline is holding this alert for another delivery attempt."),
      timestamp: alert.next_retry_at ?? alert.last_attempted_at ?? alert.sent_at,
      tone: "danger",
    });
  }

  return items;
}

function exportAlertReport(alert: AlertRecord, wardDetail: WardDetailSummary | null) {
  const rows = [
    ["Field", "Value"],
    ["Alert ID", formatAlertPublicId(alert.id)],
    ["Ward", alert.ward_name],
    ["Channel", getChannelLabel(alert.channel)],
    ["Status", getStatusLabel(alert.status)],
    ["Created", alert.created_at],
    ["Sent", alert.sent_at ?? ""],
    ["Backend", alert.delivery_backend || ""],
    ["Recipient", alert.recipient],
    ["Message", alert.message],
    ["Error", alert.error_message || ""],
    ["Ward risk level", wardDetail?.current_risk_level ?? ""],
    ["Ward risk score", wardDetail?.current_risk_score ?? ""],
  ];

  const csv = rows
    .map((row) => row.map((value) => `"${String(value).replaceAll('"', '""')}"`).join(","))
    .join("\n");

  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${formatAlertPublicId(alert.id).toLowerCase()}-report.csv`;
  link.click();
  URL.revokeObjectURL(url);
}

export default function AlertDetailPage() {
  const params = useParams<{ id: string }>();
  const { currentUser } = useAuth();
  const [alert, setAlert] = useState<AlertRecord | null>(null);
  const [wardDetail, setWardDetail] = useState<WardDetailSummary | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  const alertId = useMemo(() => Number(params.id), [params.id]);

  useEffect(() => {
    if (!currentUser || !Number.isFinite(alertId)) {
      return;
    }
    let isActive = true;

    async function loadAlertDetail() {
      setIsLoading(true);
      setError(null);

      try {
        const detail = await fetchAlertByIdViaBff(alertId);

        if (!isActive) {
          return;
        }

        if (!detail.alert) {
          setError("Alert detail is not available in your current scope.");
          setAlert(null);
          setWardDetail(null);
          return;
        }

        setAlert(detail.alert);
        setWardDetail(detail.wardDetail);
      } catch (loadError) {
        if (!isActive) {
          return;
        }

        setError(loadError instanceof Error ? loadError.message : "Unable to load alert detail.");
      } finally {
        if (isActive) {
          setIsLoading(false);
        }
      }
    }

    void loadAlertDetail();

    return () => {
      isActive = false;
    };
  }, [currentUser, alertId, refreshKey]);

  const alertType = alert ? classifyAlertType(alert) : ALERT_TYPE_META.OPERATIONAL_ALERT;
  const AlertTypeIcon = alertType.icon;
  const ChannelIcon = alert ? getChannelIcon(alert.channel) : Smartphone;
  const performance = alert ? estimateSuccessRate(alert) : 0;
  const failureCount = alert ? estimateFailureCount(alert) : 0;
  const timeline = alert ? buildTimeline(alert, alertType.triggerSource) : [];
  const riskMeaning = alert ? getRiskMeaning(alert.risk_score) : getRiskMeaning(null);
  const lastUpdatedTimestamp = getLatestTimestamp([
    alert?.sent_at,
    alert?.last_attempted_at,
    alert?.next_retry_at,
    alert?.created_at,
    wardDetail?.latest_generated_at,
    wardDetail?.updated_at,
  ]);
  const freshness = describeFreshness(lastUpdatedTimestamp, 30);
  const currentState: StateItem[] = alert
    ? [
        {
          label:
            alert.status === "DELIVERED"
              ? "Alert delivered"
              : alert.status === "FAILED"
                ? "Delivery blocked"
                : "Delivery workflow active",
          tone: alert.status === "FAILED" ? "warning" : "success",
        },
        {
          label: failureCount > 0 ? `${failureCount} failures pending review` : "No failures pending",
          tone: failureCount > 0 ? "warning" : "success",
        },
        {
          label: alert.risk_score !== null && alert.risk_score >= 75 ? "Escalation should be triggered" : "No escalation triggered",
          tone: alert.risk_score !== null && alert.risk_score >= 75 ? "warning" : "neutral",
        },
      ]
    : [];

  if (!currentUser) {
    return null;
  }

  return (
    <div className="alert-detail-dashboard">
      <DashboardTopbar
        title="Alerts"
        subtitle="Operational alert detail"
        lastUpdatedLabel={isLoading ? "Refreshing..." : formatRelativeShort(lastUpdatedTimestamp)}
        lastUpdatedTone={freshness.isStale ? "stale" : "default"}
        onRefresh={() => setRefreshKey((value) => value + 1)}
      />

      {error ? (
        <div className="status status-error">
          <AlertTriangle className="section-icon" aria-hidden="true" />
          {error}
        </div>
      ) : null}

      <section className="alert-detail-hero">
        <div className="alert-detail-hero-main">
          <div className="alert-detail-breadcrumb">
            <Link href="/alerts" className="alert-detail-back-link">
              <ArrowLeft aria-hidden="true" />
              <span>Alerts</span>
            </Link>
            <span>/</span>
            <span>{alert ? formatAlertPublicId(alert.id) : "Alert detail"}</span>
          </div>

          <div className="alert-detail-title-row">
            <div className="alert-detail-title-copy">
              <h1>{alert ? `Alert ID: ${formatAlertPublicId(alert.id)}` : "Alert detail"}</h1>
              {alert ? (
                <div className={`alert-detail-status-pill alert-detail-status-pill-${getStatusTone(alert.status)}`}>
                  <CheckCircle2 aria-hidden="true" />
                  <span>{getStatusLabel(alert.status)}</span>
                </div>
              ) : null}
            </div>

            <div className="alert-detail-actions">
              {alert ? (
                <button
                  type="button"
                  className="alert-detail-action-button alert-detail-action-button-secondary"
                  onClick={() => exportAlertReport(alert, wardDetail)}
                >
                  <Download aria-hidden="true" />
                  <span>Export Report</span>
                </button>
              ) : null}

              {alert ? (
                <Link
                  href={`/wards/${alert.ward}`}
                  className="alert-detail-action-button alert-detail-action-button-primary"
                >
                  <Share2 aria-hidden="true" />
                  <span>Share Ward Access</span>
                </Link>
              ) : null}
            </div>
          </div>
        </div>
      </section>

      {isLoading ? (
        <div className="status">
          <ShieldAlert className="section-icon" aria-hidden="true" />
          Loading alert detail...
        </div>
      ) : null}

      {!isLoading && !error && alert ? (
        <section className="alert-detail-layout">
          <div className="alert-detail-main-column">
            <article className="alert-detail-card alert-detail-overview-card">
              <div className="alert-detail-card-header">
                <h2>Alert Overview</h2>
                <span className="alert-detail-card-chip">ID: {alert.external_id || `${alert.id}-A`}</span>
              </div>

              <div className="alert-detail-overview-grid">
                <div className="alert-detail-overview-item">
                  <span>Target ward</span>
                  <strong>{alert.ward_name}</strong>
                </div>

                <div className="alert-detail-overview-item">
                  <span>Risk context</span>
                  <strong>{riskMeaning.level}</strong>
                  <small>{alert.risk_score !== null ? `Score ${Math.round(alert.risk_score)}/100, threshold 75` : "Score unavailable"}</small>
                </div>

                <div className="alert-detail-overview-item">
                  <span>Alert type</span>
                  <strong>
                    <span className={`alert-detail-type-icon alert-detail-tone-${alertType.tone}`}>
                      <AlertTypeIcon aria-hidden="true" />
                    </span>
                    {alertType.label}
                  </strong>
                  <span className="alert-detail-mini-pill">Auto-triggered</span>
                </div>

                <div className="alert-detail-overview-item">
                  <span>Trigger source</span>
                  <strong>{alertType.triggerSource}</strong>
                </div>

                <div className="alert-detail-overview-item">
                  <span>Created timestamp</span>
                  <strong>{formatTimeStamp(alert.created_at)}</strong>
                </div>
              </div>
            </article>

            <article className="alert-detail-card alert-detail-state-card">
              <div className="alert-detail-card-header">
                <h2>Current State</h2>
              </div>

              <div className="alert-detail-state-list">
                {currentState.map((item) => (
                  <div key={item.label} className={`alert-detail-state-item alert-detail-state-item-${item.tone}`}>
                    <CheckCircle2 aria-hidden="true" />
                    <span>{item.label}</span>
                  </div>
                ))}
              </div>
            </article>

            <article className="alert-detail-card alert-detail-timeline-card">
              <div className="alert-detail-card-header">
                <h2>Alert Execution Timeline</h2>
              </div>

              <div className="alert-detail-timeline">
                {timeline.map((item) => (
                  <div key={item.id} className="alert-detail-timeline-item">
                    <div className={`alert-detail-timeline-marker alert-detail-timeline-marker-${item.tone}`}>
                      {item.tone === "success" ? (
                        <CheckCircle2 aria-hidden="true" />
                      ) : item.tone === "danger" ? (
                        <XCircle aria-hidden="true" />
                      ) : item.tone === "progress" ? (
                        <ChevronRight aria-hidden="true" />
                      ) : (
                        <CircleAlert aria-hidden="true" />
                      )}
                    </div>

                    <div className="alert-detail-timeline-copy">
                      <div className="alert-detail-timeline-topline">
                        <strong>{item.title}</strong>
                        <span>{formatTimeOnly(item.timestamp)}</span>
                      </div>
                      <p>{item.description}</p>
                      {item.meta ? <small>{item.meta}</small> : null}
                    </div>
                  </div>
                ))}
              </div>
            </article>
          </div>

          <aside className="alert-detail-aside">
            <article className="alert-detail-card alert-detail-response-card">
              <div className="alert-detail-card-header">
                <h2>Response Actions</h2>
              </div>

              <div className="alert-detail-response-block">
                <span>Escalation status</span>
                <strong>{alert.risk_score !== null && alert.risk_score >= 75 ? "Escalation Required" : "Monitoring"}</strong>
              </div>

              <div className="alert-detail-response-block">
                <span>Recommended action</span>
                <strong>
                  {alert.risk_score !== null && alert.risk_score >= 75
                    ? "Start escalation protocol and notify ward facilities."
                    : "Send CHV follow-up and keep ward monitoring active."}
                </strong>
              </div>

              <div className="alert-detail-response-actions">
                <button type="button" className="alert-detail-side-button alert-detail-side-button-primary">
                  <ClipboardCheck aria-hidden="true" />
                  Start Escalation Protocol
                </button>
                <button type="button" className="alert-detail-side-button">
                  <Hospital aria-hidden="true" />
                  Notify Facilities
                </button>
                <button type="button" className="alert-detail-side-button">
                  <MessageSquareWarning aria-hidden="true" />
                  Send Follow-up Message
                </button>
              </div>
            </article>

            <article className="alert-detail-card alert-detail-performance-card">
              <div className="alert-detail-card-header">
                <h2>Delivery Performance</h2>
                <div className="alert-detail-performance-bars" aria-hidden="true">
                  <span />
                  <span />
                  <span />
                </div>
              </div>

              <div className="alert-detail-performance-ring">
                <svg viewBox="0 0 120 120" aria-hidden="true">
                  <circle cx="60" cy="60" r="46" className="alert-detail-ring-track" />
                  <circle
                    cx="60"
                    cy="60"
                    r="46"
                    className="alert-detail-ring-progress"
                    style={{
                      strokeDasharray: `${2 * Math.PI * 46}`,
                      strokeDashoffset: `${2 * Math.PI * 46 * (1 - performance / 100)}`,
                    }}
                  />
                </svg>
                <div className="alert-detail-performance-copy">
                  <div>
                    <strong>{performance}%</strong>
                    <span>{alert.status === "DELIVERED" ? "Success" : alert.status === "FAILED" ? "Blocked" : "Active"}</span>
                  </div>
                </div>
              </div>

              <dl className="alert-detail-performance-list">
                <div>
                  <dt>Channel</dt>
                  <dd>{alert.channel === "SMS" ? "SMS Bulk (Global)" : getChannelLabel(alert.channel)}</dd>
                </div>
                <div>
                  <dt>Total recipients</dt>
                  <dd>{alert.channel === "SMS" ? "1,240 CHVs & Officials" : getChannelAudience(alert.channel)}</dd>
                </div>
                <div>
                  <dt>Retry attempts</dt>
                  <dd>
                    {alert.max_attempts > 1 ? `${alert.max_attempts} Automated` : `${alert.attempt_count} of ${alert.max_attempts}`}
                  </dd>
                </div>
                <div>
                  <dt>Failed deliveries</dt>
                  <dd>{failureCount > 0 ? `${failureCount} recipient${failureCount > 1 ? "s" : ""}` : "None"}</dd>
                </div>
                <div>
                  <dt>Failure reason</dt>
                  <dd>{alert.error_message || "No active failure reason"}</dd>
                </div>
              </dl>
            </article>

            <article className="alert-detail-card alert-detail-ward-card">
              <div className="alert-detail-ward-map">
                <div className="alert-detail-ward-map-overlay">
                  <span>View Ward Risk Map</span>
                </div>
              </div>

              <div className="alert-detail-ward-copy">
                <h3>Ward Risk Detail</h3>
                <p>
                  {wardDetail
                    ? `${wardDetail.name} is currently ${wardDetail.current_risk_level === "HIGH" ? "under elevated watch" : "within routine watch"} with ${wardDetail.current_risk_level.toLowerCase()} risk and ${riskMeaning.trend.toLowerCase()} trend.`
                    : `${alert.ward_name} remains the current operational ward linked to this alert.`}
                </p>
                <div className="alert-detail-ward-actions">
                  <Link href={`/wards/${alert.ward}`} className="alert-detail-inline-link">
                    View Full Ward Analysis
                    <ChevronRight aria-hidden="true" />
                  </Link>
                  <button type="button" className="alert-detail-inline-button">
                    Compare Neighboring Wards
                  </button>
                </div>
              </div>
            </article>

            <div className="alert-detail-side-actions">
              <button
                type="button"
                className="alert-detail-side-button alert-detail-side-button-danger"
                disabled={failureCount === 0}
              >
                <AlertTriangle aria-hidden="true" />
                Re-send to failures {failureCount > 0 ? `(${failureCount})` : ""}
              </button>
              <button type="button" className="alert-detail-side-button" disabled>
                <XCircle aria-hidden="true" />
                Recall Alert
              </button>
            </div>
          </aside>
        </section>
      ) : null}
    </div>
  );
}
