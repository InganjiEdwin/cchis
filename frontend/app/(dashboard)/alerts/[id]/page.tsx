"use client";

import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  ChevronRight,
  CircleAlert,
  CloudRain,
  Download,
  Droplets,
  Radio,
  Share2,
  ShieldAlert,
  Smartphone,
  Waves,
  XCircle,
} from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useMemo, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { DashboardTopbar } from "@/components/dashboard-topbar";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { StatusBanner } from "@/components/ui/status-banner";
import { StatusBadge } from "@/components/ui/status-badge";
import { cn } from "@/lib/cn";
import { type AlertRecord, type WardDetailSummary } from "@/lib/dashboard";
import { describeFreshness, getLatestTimestamp } from "@/lib/freshness";
import { useAlertDetailQuery } from "@/queries/use-alert-detail-query";

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
  tone: "primary" | "progress" | "success" | "danger" | "warning" | "neutral";
  category: "all" | "delivery" | "responses" | "system";
  meta?: string;
  details?: string[];
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
      return "success" as const;
    case "FAILED":
      return "danger" as const;
    case "RETRY_PENDING":
      return "warning" as const;
    case "QUEUED":
    default:
      return "default" as const;
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
      id: "triggered",
      title: "Alert triggered",
      description: `Alert generated by the risk model using ${triggerSource.toLowerCase()} signals.`,
      timestamp: alert.created_at,
      tone: "primary",
      meta: alert.risk_score !== null ? `Risk score: ${Math.round(alert.risk_score)}/100` : undefined,
      category: "system",
      details: [
        `Trigger source: ${triggerSource}`,
      ],
    },
    {
      id: "created",
      title: "Alert record created",
      description: `A ${getChannelLabel(alert.channel).toLowerCase()} record was created for ${alert.ward_name}.`,
      timestamp: alert.created_at,
      tone: "neutral",
      category: "system",
      details: [
        `Recipient: ${alert.recipient}`,
        `Channel: ${getChannelLabel(alert.channel)}`,
      ],
    },
    {
      id: "dispatch",
      title: "Delivery attempt state",
      description: `Latest delivery activity is tracked through ${alert.delivery_backend || "the recorded backend"}.`,
      timestamp: alert.last_attempted_at ?? alert.sent_at ?? alert.created_at,
      tone: alert.status === "FAILED" ? "danger" : alert.status === "DELIVERED" ? "success" : "progress",
      category: "delivery",
      details: [
        `Attempt count: ${alert.attempt_count}/${alert.max_attempts}`,
        `Backend: ${alert.delivery_backend || "Unspecified"}`,
      ],
    },
    {
      id: "delivery-status",
      title: "Recorded delivery outcome",
      description:
        alert.status === "DELIVERED"
          ? "This alert record is marked as delivered."
          : alert.status === "FAILED"
            ? "This alert record is marked as failed and needs operator review."
            : alert.status === "RETRY_PENDING"
              ? "This alert record is waiting for another delivery attempt."
              : "This alert record is queued and awaiting delivery processing.",
      timestamp: alert.sent_at ?? alert.last_attempted_at,
      tone: alert.status === "DELIVERED" ? "success" : alert.status === "FAILED" ? "danger" : "warning",
      category: "delivery",
      details: [
        `Status: ${getStatusLabel(alert.status)}`,
        `Last attempted at: ${formatTimeStamp(alert.last_attempted_at)}`,
        `Sent at: ${formatTimeStamp(alert.sent_at)}`,
      ],
    },
  ];

  if (alert.next_retry_at) {
    items.push({
      id: "retry",
      title: "Next retry scheduled",
      description: "The backend has recorded a future retry time for this alert record.",
      timestamp: alert.next_retry_at,
      tone: "warning",
      category: "delivery",
      details: [`Next retry at: ${formatTimeStamp(alert.next_retry_at)}`],
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

export default function AlertDetailPage() {
  const params = useParams<{ id: string }>();
  const { currentUser } = useAuth();
  const [timelineFilter, setTimelineFilter] = useState<"all" | "delivery" | "responses" | "system">("all");
  const [expandedTimelineItemId, setExpandedTimelineItemId] = useState<string | null>("delivery-status");

  const alertId = useMemo(() => Number(params.id), [params.id]);
  const alertDetailQuery = useAlertDetailQuery({
    alertId,
    enabled: Boolean(currentUser) && Number.isFinite(alertId),
  });
  const alert = alertDetailQuery.data?.alert ?? null;
  const wardDetail = alertDetailQuery.data?.wardDetail ?? null;
  const isLoading = alertDetailQuery.isPending;
  const isRefreshing = alertDetailQuery.isFetching;
  const error =
    alertDetailQuery.error instanceof Error
      ? alertDetailQuery.error.message
      : !isLoading && alertDetailQuery.data && !alertDetailQuery.data.alert
        ? "Alert detail is not available in your current scope."
        : null;

  const alertType = alert ? classifyAlertType(alert) : ALERT_TYPE_META.OPERATIONAL_ALERT;
  const AlertTypeIcon = alertType.icon;
  const timeline = alert ? buildTimeline(alert, alertType.triggerSource) : [];
  const filteredTimeline = timeline.filter((item) => timelineFilter === "all" || item.category === timelineFilter);
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
                : "Delivery still in progress",
          tone: alert.status === "FAILED" ? "warning" : "success",
        },
        {
          label:
            alert.status === "FAILED"
              ? "This alert record failed delivery"
              : alert.status === "RETRY_PENDING"
                ? "A retry is still pending"
                : "No active delivery failure recorded",
          tone: alert.status === "FAILED" || alert.status === "RETRY_PENDING" ? "warning" : "success",
        },
        {
          label:
            alert.risk_score !== null && alert.risk_score >= 75
              ? "High ward risk accompanies this alert"
              : "No high ward-risk threshold recorded",
          tone: alert.risk_score !== null && alert.risk_score >= 75 ? "warning" : "neutral",
        },
      ]
    : [];

  if (!currentUser) {
    return null;
  }

  return (
    <div className="space-y-6">
      <DashboardTopbar
        title="Alerts"
        subtitle="Operational alert detail"
        lastUpdatedLabel={isRefreshing ? "Refreshing..." : formatRelativeShort(lastUpdatedTimestamp)}
        lastUpdatedTone={freshness.isStale ? "stale" : "default"}
        onRefresh={() => {
          void alertDetailQuery.refetch();
        }}
      />

      {error ? (
        <StatusBanner tone="danger" icon={<AlertTriangle aria-hidden="true" />}>
          {error}
        </StatusBanner>
      ) : null}

      <section className="space-y-5">
        <div className="flex flex-wrap items-center gap-3 text-sm text-panel-muted">
          <Link
            href="/alerts"
            className="inline-flex items-center gap-2 font-semibold text-panel-copy transition hover:text-panel-strong"
          >
            <ArrowLeft className="size-4" aria-hidden="true" />
            Alerts
          </Link>
          <span>/</span>
          <span>{alert ? formatAlertPublicId(alert.id) : "Alert detail"}</span>
        </div>

        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-3">
              <h1 className="text-[clamp(2rem,1.35rem+2vw,3rem)] font-semibold leading-tight text-panel-strong">
                {alert ? `Alert ID: ${formatAlertPublicId(alert.id)}` : "Alert detail"}
              </h1>
              {alert ? (
                <StatusBadge tone={getStatusTone(alert.status)} className="rounded-full px-3 py-1.5 tracking-[0.14em]">
                  {getStatusLabel(alert.status)}
                </StatusBadge>
              ) : null}
            </div>
            <p className="max-w-3xl text-sm text-panel-muted">
              Review delivery status, ward risk context, and the available read-path context for this alert.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            {alert ? (
              <Button variant="secondary" className="px-4" onClick={() => exportAlertReport(alert, wardDetail)}>
                <Download className="size-4" aria-hidden="true" />
                <span>Export Report</span>
              </Button>
            ) : null}

            {alert ? (
              <Link
                href={`/wards/${alert.ward}`}
                className="inline-flex h-11 items-center justify-center gap-2 rounded-pill bg-[var(--login-submit-start)] px-4 text-sm font-semibold text-white shadow-[var(--login-submit-shadow)] transition hover:bg-[var(--login-submit-end)] hover:shadow-[var(--login-submit-shadow-hover)]"
              >
                <Share2 className="size-4" aria-hidden="true" />
                <span>Open Ward Detail</span>
              </Link>
            ) : null}
          </div>
        </div>
      </section>

      {isLoading ? (
        <StatusBanner tone="info" icon={<ShieldAlert aria-hidden="true" />}>
          Loading alert detail...
        </StatusBanner>
      ) : null}

      {!isLoading && !error && alert ? (
        <section className="grid gap-5 xl:grid-cols-[minmax(0,1.35fr)_22rem]">
          <div className="space-y-5">
            <Card className="rounded-[2rem] px-5 py-5 sm:px-6">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <h2 className="text-2xl font-semibold text-panel-strong">Alert Overview</h2>
                <span className="inline-flex rounded-full border border-panel-table-wrap px-3 py-1 text-xs font-semibold uppercase tracking-[0.14em] text-panel-subtle">
                  ID: {alert.external_id || `${alert.id}-A`}
                </span>
              </div>

              <div className="mt-6 grid gap-5 md:grid-cols-2 xl:grid-cols-3">
                <div className="space-y-2">
                  <span className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-subtle">Target ward</span>
                  <strong className="block text-base text-panel-strong">{alert.ward_name}</strong>
                </div>
                <div className="space-y-2">
                  <span className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-subtle">Risk context</span>
                  <strong className="block text-base text-panel-strong">{riskMeaning.level}</strong>
                  <small className="text-sm text-panel-muted">
                    {alert.risk_score !== null ? `Score ${Math.round(alert.risk_score)}/100, threshold 75` : "Score unavailable"}
                  </small>
                </div>
                <div className="space-y-2">
                  <span className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-subtle">Alert type</span>
                  <div className="flex flex-wrap items-center gap-3">
                    <span className={cn("inline-flex size-10 items-center justify-center rounded-2xl", getToneSurface(alertType.tone))}>
                      <AlertTypeIcon className="size-5" aria-hidden="true" />
                    </span>
                    <strong className="text-base text-panel-strong">{alertType.label}</strong>
                  </div>
                  <StatusBadge tone="info" className="tracking-[0.12em]">
                    Backend record
                  </StatusBadge>
                </div>
                <div className="space-y-2">
                  <span className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-subtle">Trigger source</span>
                  <strong className="block text-base text-panel-strong">{alertType.triggerSource}</strong>
                </div>
                <div className="space-y-2">
                  <span className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-subtle">Created timestamp</span>
                  <strong className="block text-base text-panel-strong">{formatTimeStamp(alert.created_at)}</strong>
                </div>
              </div>
            </Card>

            <Card className="rounded-[2rem] px-5 py-5 sm:px-6">
              <h2 className="text-2xl font-semibold text-panel-strong">Current State</h2>
              <div className="mt-5 flex flex-col gap-3">
                {currentState.map((item) => (
                  <div
                    key={item.label}
                    className={cn(
                      "flex items-center gap-3 rounded-2xl px-4 py-3 text-sm font-medium",
                      item.tone === "success" &&
                        "bg-[color-mix(in_srgb,var(--success)_10%,white)] text-[color:var(--success)] dark:bg-[color-mix(in_srgb,var(--success)_16%,transparent)]",
                      item.tone === "warning" &&
                        "bg-[color-mix(in_srgb,var(--warning)_12%,white)] text-[color:var(--warning)] dark:bg-[color-mix(in_srgb,var(--warning)_18%,transparent)]",
                      item.tone === "neutral" &&
                        "bg-[color-mix(in_srgb,var(--dashboard-table-line)_60%,transparent)] text-panel-copy",
                    )}
                  >
                    <CheckCircle2 className="size-4 shrink-0" aria-hidden="true" />
                    <span>{item.label}</span>
                  </div>
                ))}
              </div>
            </Card>

            <Card className="rounded-[2rem] px-5 py-5 sm:px-6">
              <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                <div>
                  <h2 className="text-2xl font-semibold text-panel-strong">Alert Execution Timeline</h2>
                  <p className="mt-2 text-sm text-panel-muted">
                    Record-based lifecycle from trigger through the actual backend delivery state changes we can verify today.
                  </p>
                </div>
                <StatusBadge
                  tone={alert.status === "FAILED" ? "danger" : alert.status === "DELIVERED" ? "success" : "warning"}
                  className="px-3 py-1.5 tracking-[0.14em]"
                >
                  {alert.status === "FAILED" ? "Needs review" : alert.status === "DELIVERED" ? "Delivered" : "Awaiting completion"}
                </StatusBadge>
              </div>

              <div className="mt-6 grid gap-4 md:grid-cols-4">
                <Card className="rounded-[1.4rem] bg-[color-mix(in_srgb,var(--dashboard-table-line)_18%,transparent)] px-4 py-4 shadow-none">
                  <p className="text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle">Recipient</p>
                  <p className="mt-2 text-2xl font-semibold tracking-[-0.04em] text-panel-strong">
                    1
                  </p>
                </Card>
                <Card className="rounded-[1.4rem] bg-[color-mix(in_srgb,var(--dashboard-table-line)_18%,transparent)] px-4 py-4 shadow-none">
                  <p className="text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle">Attempt count</p>
                  <p className="mt-2 text-2xl font-semibold tracking-[-0.04em] text-panel-strong">
                    {alert.attempt_count}/{alert.max_attempts}
                  </p>
                </Card>
                <Card className="rounded-[1.4rem] bg-[color-mix(in_srgb,var(--dashboard-table-line)_18%,transparent)] px-4 py-4 shadow-none">
                  <p className="text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle">Backend</p>
                  <p className="mt-2 text-lg font-semibold tracking-[-0.04em] text-panel-strong">{alert.delivery_backend || "Unspecified"}</p>
                </Card>
                <Card className="rounded-[1.4rem] bg-[color-mix(in_srgb,var(--dashboard-table-line)_18%,transparent)] px-4 py-4 shadow-none">
                  <p className="text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle">Next retry</p>
                  <p className="mt-2 text-lg font-semibold tracking-[-0.04em] text-panel-strong">
                    {alert.next_retry_at ? formatTimeOnly(alert.next_retry_at) : "None"}
                  </p>
                </Card>
              </div>

              <div className="mt-6 flex flex-wrap gap-2">
                {[
                  { value: "all", label: "All" },
                  { value: "delivery", label: "Delivery" },
                  { value: "responses", label: "Responses" },
                  { value: "system", label: "System Events" },
                ].map((filter) => (
                  <button
                    key={filter.value}
                    type="button"
                    className={cn(
                      "inline-flex h-10 items-center justify-center rounded-pill border px-4 text-sm font-semibold transition",
                      timelineFilter === filter.value
                        ? "border-brand bg-brand text-white"
                        : "border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] text-panel-copy hover:border-[var(--dashboard-icon-button-border)] hover:text-panel-strong",
                    )}
                    onClick={() => setTimelineFilter(filter.value as "all" | "delivery" | "responses" | "system")}
                  >
                    {filter.label}
                  </button>
                ))}
              </div>

              <div className="mt-6 space-y-5">
                {filteredTimeline.map((item, index) => (
                  <div key={item.id} className="flex gap-4">
                    <div className="flex flex-col items-center">
                      <span
                        className={cn(
                          "inline-flex size-10 items-center justify-center rounded-full",
                          item.tone === "primary" && "bg-[color-mix(in_srgb,var(--brand)_12%,white)] text-brand dark:bg-[color-mix(in_srgb,var(--brand)_18%,transparent)]",
                          item.tone === "progress" && "bg-[color-mix(in_srgb,var(--warning)_12%,white)] text-[color:var(--warning)] dark:bg-[color-mix(in_srgb,var(--warning)_18%,transparent)]",
                          item.tone === "success" && "bg-[color-mix(in_srgb,var(--success)_12%,white)] text-[color:var(--success)] dark:bg-[color-mix(in_srgb,var(--success)_18%,transparent)]",
                          item.tone === "danger" && "bg-[color-mix(in_srgb,var(--danger)_12%,white)] text-[color:var(--danger)] dark:bg-[color-mix(in_srgb,var(--danger)_18%,transparent)]",
                          item.tone === "warning" && "bg-[color-mix(in_srgb,var(--warning)_14%,white)] text-[color:var(--warning)] dark:bg-[color-mix(in_srgb,var(--warning)_20%,transparent)]",
                          item.tone === "neutral" && "bg-[color-mix(in_srgb,var(--dashboard-table-line)_60%,transparent)] text-panel-copy",
                        )}
                      >
                        {item.tone === "success" ? (
                          <CheckCircle2 className="size-4" aria-hidden="true" />
                        ) : item.tone === "danger" ? (
                          <XCircle className="size-4" aria-hidden="true" />
                        ) : item.tone === "progress" ? (
                          <ChevronRight className="size-4" aria-hidden="true" />
                        ) : item.tone === "warning" ? (
                          <AlertTriangle className="size-4" aria-hidden="true" />
                        ) : (
                          <CircleAlert className="size-4" aria-hidden="true" />
                        )}
                      </span>
                      {index < filteredTimeline.length - 1 ? (
                        <span className="mt-2 h-full min-h-10 w-px bg-panel-table-wrap" aria-hidden="true" />
                      ) : null}
                    </div>

                    <div className="flex-1 pb-2">
                      <button
                        type="button"
                        className="w-full rounded-[1.2rem] border border-panel-table-wrap bg-[color-mix(in_srgb,var(--dashboard-table-line)_18%,transparent)] px-4 py-4 text-left transition hover:border-[var(--dashboard-icon-button-border)]"
                        onClick={() =>
                          setExpandedTimelineItemId((currentValue) => (currentValue === item.id ? null : item.id))
                        }
                      >
                        <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                          <strong className="text-base text-panel-strong">{item.title}</strong>
                          <span className="shrink-0 text-xs font-semibold uppercase tracking-[0.14em] text-panel-subtle">
                            {formatTimeOnly(item.timestamp)}
                          </span>
                        </div>
                        <p className="mt-2 text-sm leading-6 text-panel-copy">{item.description}</p>
                        {item.meta ? <small className="mt-2 block text-sm text-panel-muted">{item.meta}</small> : null}
                        {expandedTimelineItemId === item.id && item.details?.length ? (
                          <div className="mt-4 space-y-2 border-t border-panel-table-wrap pt-4">
                            {item.details.map((detail) => (
                              <div key={detail} className="flex items-start gap-2 text-sm text-panel-muted">
                                <span className="mt-2 size-1.5 shrink-0 rounded-full bg-[var(--dashboard-subtle-copy)]" />
                                <span>{detail}</span>
                              </div>
                            ))}
                          </div>
                        ) : null}
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </Card>
          </div>

          <div className="space-y-5">
            <Card className="rounded-[2rem] bg-[linear-gradient(180deg,color-mix(in_srgb,var(--brand)_10%,var(--panel)),var(--panel))] px-5 py-5">
              <h2 className="text-2xl font-semibold text-panel-strong">Response Actions</h2>

              <div className="mt-5 space-y-5">
                <div className="space-y-1">
                  <span className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-subtle">Derived escalation posture</span>
                  <strong className="block text-base text-panel-strong">
                    {alert.risk_score !== null && alert.risk_score >= 75 ? "Elevated review needed" : "Monitoring"}
                  </strong>
                </div>
                <div className="space-y-1">
                  <span className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-subtle">Suggested review path</span>
                  <strong className="block text-base leading-6 text-panel-strong">
                    {alert.risk_score !== null && alert.risk_score >= 75
                      ? "Review ward detail and backend delivery state before escalating outside this page."
                      : "Continue monitoring this record and use ward detail for deeper context."}
                  </strong>
                </div>
              </div>

              <div className="mt-6 flex flex-col gap-3">
                <StatusBanner tone="warning" icon={<ShieldAlert aria-hidden="true" />}>
                  Escalation, facility notification, and follow-up messaging actions are not backend-wired from this alert detail page yet.
                </StatusBanner>
                <Button className="w-full justify-center" disabled>
                  Escalation Workflow Pending
                </Button>
                <Button variant="secondary" className="w-full justify-center" disabled>
                  Notify Facilities
                </Button>
                <Button variant="secondary" className="w-full justify-center" disabled>
                  Send Follow-up Message
                </Button>
              </div>
            </Card>

            <Card className="rounded-[2rem] px-5 py-5">
              <div className="flex items-start justify-between gap-4">
                <h2 className="text-2xl font-semibold text-panel-strong">Delivery Record</h2>
              </div>

              <dl className="mt-6 space-y-4 border-t border-panel-table-wrap pt-5 text-sm">
                {[
                  ["Channel", getChannelLabel(alert.channel)],
                  ["Audience label", getChannelAudience(alert.channel)],
                  ["Recipient", alert.recipient],
                  ["Attempt count", `${alert.attempt_count} of ${alert.max_attempts}`],
                  ["External ID", alert.external_id || "No external ID recorded"],
                  ["Failure reason", alert.error_message || "No active failure reason"],
                ].map(([label, value]) => (
                  <div key={label} className="flex items-start justify-between gap-4">
                    <dt className="text-panel-muted">{label}</dt>
                    <dd className="max-w-[12rem] text-right font-semibold text-panel-strong">{value}</dd>
                  </div>
                ))}
              </dl>
            </Card>

            <Card className="rounded-[2rem] overflow-hidden p-0">
              <div className="relative h-40 bg-[radial-gradient(circle_at_top_left,color-mix(in_srgb,var(--brand)_12%,transparent),transparent_45%),linear-gradient(135deg,color-mix(in_srgb,var(--panel)_92%,white),var(--panel))]">
                <div className="absolute inset-0 bg-[linear-gradient(90deg,color-mix(in_srgb,var(--dashboard-table-line)_28%,transparent)_1px,transparent_1px),linear-gradient(color-mix(in_srgb,var(--dashboard-table-line)_28%,transparent)_1px,transparent_1px)] bg-[size:3.5rem_3.5rem] opacity-60" />
                <div className="absolute inset-x-6 bottom-5">
                  <div className="inline-flex rounded-full bg-panel/90 px-4 py-2 text-xs font-semibold uppercase tracking-[0.16em] text-panel-strong shadow-sm backdrop-blur">
                    View Ward Risk Map
                  </div>
                </div>
              </div>

              <div className="space-y-4 px-5 py-5">
                <h3 className="text-xl font-semibold text-panel-strong">Ward Risk Detail</h3>
                <p className="text-sm leading-6 text-panel-copy">
                  {wardDetail
                    ? `${wardDetail.name} is currently ${wardDetail.current_risk_level === "HIGH" ? "under elevated watch" : "within routine watch"} with ${wardDetail.current_risk_level.toLowerCase()} risk and ${riskMeaning.trend.toLowerCase()} trend.`
                    : `${alert.ward_name} remains the current operational ward linked to this alert.`}
                </p>
                <div className="flex flex-col gap-3">
                  <Link
                    href={`/wards/${alert.ward}`}
                    className="inline-flex items-center gap-2 text-sm font-semibold text-brand transition hover:text-[var(--dashboard-sidebar-title)]"
                  >
                    View Full Ward Analysis
                    <ChevronRight className="size-4" aria-hidden="true" />
                  </Link>
                  <button
                    type="button"
                    disabled
                    className="inline-flex items-center justify-center rounded-pill border border-panel-table-wrap px-4 py-3 text-sm font-semibold text-panel-copy transition hover:border-[var(--dashboard-icon-button-border)] hover:text-panel-strong"
                  >
                    Compare Neighboring Wards Pending
                  </button>
                </div>
              </div>
            </Card>

            <div className="flex flex-col gap-3">
              <Button variant="danger" className="w-full justify-center" disabled>
                Re-send Pending Backend Contract
              </Button>
              <Button variant="secondary" className="w-full justify-center" disabled>
                Recall Alert Pending Backend Contract
              </Button>
            </div>
          </div>
        </section>
      ) : null}
    </div>
  );
}
