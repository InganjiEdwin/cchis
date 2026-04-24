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
import { useAlertDetailQuery } from "@/queries/use-alert-detail-query";

type AlertTypeMeta = {
  icon: typeof Droplets;
};

function getClassificationIcon(iconKey: string): AlertTypeMeta["icon"] {
  switch (iconKey) {
    case "droplets":
      return Droplets;
    case "waves":
      return Waves;
    case "circle-alert":
      return CircleAlert;
    case "cloud-rain":
      return CloudRain;
    case "shield-alert":
    default:
      return ShieldAlert;
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

function exportAlertReport(alert: AlertRecord, wardDetail: WardDetailSummary | null) {
  const rows = [
    ["Field", "Value"],
    ["Alert ID", formatAlertPublicId(alert.id)],
    ["Ward", alert.ward_name],
    ["Channel", alert.channel],
    ["Status", alert.status],
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

function getToneSurface(tone: "red" | "amber" | "orange" | "blue" | "slate") {
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
  const wardDetail = alertDetailQuery.data?.ward_detail ?? null;
  const classification = alertDetailQuery.data?.classification ?? null;
  const riskContext = alertDetailQuery.data?.risk_context ?? null;
  const delivery = alertDetailQuery.data?.delivery ?? null;
  const currentState = alertDetailQuery.data?.current_state ?? [];
  const freshness = alertDetailQuery.data?.freshness ?? null;
  const timeline = alertDetailQuery.data?.timeline ?? [];
  const capabilities = alertDetailQuery.data?.capabilities ?? null;
  const isLoading = alertDetailQuery.isPending;
  const isRefreshing = alertDetailQuery.isFetching;
  const error =
    alertDetailQuery.error instanceof Error
      ? alertDetailQuery.error.message
      : !isLoading && alertDetailQuery.data && !alertDetailQuery.data.alert
        ? "Alert detail is not available in your current scope."
        : null;
  const filteredTimeline = timeline.filter((item) => timelineFilter === "all" || item.category === timelineFilter);
  const lastUpdatedTimestamp = freshness?.updated_at ?? null;
  const AlertTypeIcon = classification ? getClassificationIcon(classification.icon_key) : ShieldAlert;

  if (!currentUser) {
    return null;
  }

  return (
    <div className="space-y-6">
      <DashboardTopbar
        title="Alerts"
        subtitle="Alert record detail"
        lastUpdatedLabel={isRefreshing ? "Refreshing..." : formatRelativeShort(lastUpdatedTimestamp)}
        lastUpdatedTone={freshness?.is_stale ? "stale" : "default"}
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
              {alert && delivery ? (
                <StatusBadge tone={delivery.status_tone} className="rounded-full px-3 py-1.5 tracking-[0.14em]">
                  {delivery.status_label}
                </StatusBadge>
              ) : null}
            </div>
            <p className="max-w-3xl text-sm text-panel-muted">
              Review recorded delivery status, linked ward context, and the available read-path details for this alert.
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
                <h2 className="text-2xl font-semibold text-panel-strong">Alert Record Summary</h2>
                <span className="inline-flex rounded-full border border-panel-table-wrap px-3 py-1 text-xs font-semibold uppercase tracking-[0.14em] text-panel-subtle">
                  ID: {alert.external_id || `${alert.id}-A`}
                </span>
              </div>

              <div className="mt-6 grid gap-5 md:grid-cols-2 xl:grid-cols-3">
                <div className="space-y-2">
                  <span className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-subtle">Linked ward</span>
                  <strong className="block text-base text-panel-strong">{alert.ward_name}</strong>
                </div>
                <div className="space-y-2">
                  <span className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-subtle">Risk context</span>
                  <strong className="block text-base text-panel-strong">{riskContext?.level_label ?? "Risk unavailable"}</strong>
                  <small className="text-sm text-panel-muted">
                    {riskContext?.recorded_risk_score !== null && riskContext?.recorded_risk_score !== undefined
                      ? `Score ${Math.round(riskContext.recorded_risk_score)}/100${riskContext.threshold ? `, threshold ${riskContext.threshold}` : ""}`
                      : "Score unavailable"}
                  </small>
                </div>
                <div className="space-y-2">
                  <span className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-subtle">Alert type</span>
                  <div className="flex flex-wrap items-center gap-3">
                    <span className={cn("inline-flex size-10 items-center justify-center rounded-2xl", getToneSurface(classification?.tone ?? "slate"))}>
                      <AlertTypeIcon className="size-5" aria-hidden="true" />
                    </span>
                    <strong className="text-base text-panel-strong">{classification?.label ?? "Alert record"}</strong>
                  </div>
                  <StatusBadge tone="info" className="tracking-[0.12em]">
                    {classification?.mode === "derived_from_record_text" ? "Derived from record text" : "Backend record"}
                  </StatusBadge>
                </div>
                <div className="space-y-2">
                  <span className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-subtle">Trigger source</span>
                  <strong className="block text-base text-panel-strong">{classification?.trigger_source ?? "Not recorded"}</strong>
                </div>
                <div className="space-y-2">
                  <span className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-subtle">Created timestamp</span>
                  <strong className="block text-base text-panel-strong">{formatTimeStamp(alert.created_at)}</strong>
                </div>
              </div>
            </Card>

            <Card className="rounded-[2rem] px-5 py-5 sm:px-6">
              <h2 className="text-2xl font-semibold text-panel-strong">Recorded State</h2>
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
                  <h2 className="text-2xl font-semibold text-panel-strong">Alert Record Timeline</h2>
                  <p className="mt-2 text-sm text-panel-muted">
                    Recorded timeline for this alert, from creation through the delivery-state changes visible on this record.
                  </p>
                </div>
                <StatusBadge
                  tone={delivery?.status_tone ?? "warning"}
                  className="px-3 py-1.5 tracking-[0.14em]"
                >
                  {delivery?.status_label ?? "Delivery state unavailable"}
                </StatusBadge>
              </div>

              <div className="mt-6 grid gap-4 md:grid-cols-4">
                <Card className="rounded-[1.4rem] bg-[color-mix(in_srgb,var(--dashboard-table-line)_18%,transparent)] px-4 py-4 shadow-none">
                  <p className="text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle">Recipient count</p>
                  <p className="mt-2 text-2xl font-semibold tracking-[-0.04em] text-panel-strong">
                    {delivery?.recipient_count ?? 1}
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
                  { value: "responses", label: "Review items" },
                  { value: "system", label: "System records" },
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
              <h2 className="text-2xl font-semibold text-panel-strong">Review Guidance</h2>

              <div className="mt-5 space-y-5">
                <div className="space-y-1">
                  <span className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-subtle">Review posture</span>
                  <strong className="block text-base text-panel-strong">
                    {riskContext?.trend_label ?? "Monitoring"}
                  </strong>
                </div>
                <div className="space-y-1">
                  <span className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-subtle">Recorded review summary</span>
                  <strong className="block text-base leading-6 text-panel-strong">
                    {riskContext?.summary ?? "Continue monitoring this record and use ward detail for recorded ward context."}
                  </strong>
                </div>
              </div>

              <div className="mt-6 flex flex-col gap-3">
                <StatusBanner tone="warning" icon={<ShieldAlert aria-hidden="true" />}>
                  Escalation, facility notification, follow-up messaging, resend, and recall actions are not backend-wired from this alert detail page.
                </StatusBanner>
                <Button className="w-full justify-center" disabled={!capabilities || !capabilities.can_resend}>
                  Escalation Action Unavailable
                </Button>
                <Button variant="secondary" className="w-full justify-center" disabled={!capabilities || !capabilities.can_notify_facilities}>
                  Facility Notification Unavailable
                </Button>
                <Button variant="secondary" className="w-full justify-center" disabled={!capabilities || !capabilities.can_send_follow_up}>
                  Follow-up Message Unavailable
                </Button>
              </div>
            </Card>

            <Card className="rounded-[2rem] px-5 py-5">
              <div className="flex items-start justify-between gap-4">
                <h2 className="text-2xl font-semibold text-panel-strong">Delivery Record</h2>
              </div>

              <dl className="mt-6 space-y-4 border-t border-panel-table-wrap pt-5 text-sm">
                {[
                  ["Channel", delivery?.channel_label ?? alert.channel],
                  ["Audience", delivery?.audience_label ?? "Recorded recipient"],
                  ["Recipient", alert.recipient],
                  ["Attempt count", `${alert.attempt_count} of ${alert.max_attempts}`],
                  ["External ID", alert.external_id || "No external ID recorded"],
                  ["Failure reason", alert.error_message || "No failure reason recorded"],
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
                    Ward risk context
                  </div>
                </div>
              </div>

              <div className="space-y-4 px-5 py-5">
                <h3 className="text-xl font-semibold text-panel-strong">Ward Context</h3>
                <p className="text-sm leading-6 text-panel-copy">
                  {wardDetail
                    ? `${wardDetail.name} is the linked ward summary for this alert and currently shows ${wardDetail.current_risk_level.toLowerCase()} recorded ward risk.`
                    : `${alert.ward_name} remains the ward linked to this alert record.`}
                </p>
                <div className="flex flex-col gap-3">
                  <Link
                    href={`/wards/${alert.ward}`}
                    className="inline-flex items-center gap-2 text-sm font-semibold text-brand transition hover:text-[var(--dashboard-sidebar-title)]"
                  >
                    Open Ward Detail
                    <ChevronRight className="size-4" aria-hidden="true" />
                  </Link>
                </div>
              </div>
            </Card>

            <div className="flex flex-col gap-3">
              <Button variant="danger" className="w-full justify-center" disabled={!capabilities || !capabilities.can_resend}>
                Resend Unavailable
              </Button>
              <Button variant="secondary" className="w-full justify-center" disabled={!capabilities || !capabilities.can_recall}>
                Recall Unavailable
              </Button>
            </div>
          </div>
        </section>
      ) : null}
    </div>
  );
}
