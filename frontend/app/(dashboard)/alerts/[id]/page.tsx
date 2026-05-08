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
  Share2,
  ShieldAlert,
  Waves,
  XCircle,
} from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { DashboardTopbar } from "@/components/dashboard-topbar";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { StatusBanner } from "@/components/ui/status-banner";
import { StatusBadge } from "@/components/ui/status-badge";
import { cn } from "@/lib/cn";
import {
  createSensitiveExportViaBff,
  downloadSensitiveExportFile,
  downloadSensitiveExportViaBff,
  type AlertRecord,
  type ClimateEvidence,
} from "@/lib/dashboard";
import { hasActionCapability } from "@/lib/capabilities";
import { canExportSensitiveReports } from "@/lib/roles";
import { useAlertDetailQuery } from "@/queries/use-alert-detail-query";
import { useCreateChvCoverageRequestFromAlertMutation } from "@/queries/use-create-chv-coverage-request-from-alert-mutation";
import { useCreateChvCoverageRequestMutation } from "@/queries/use-create-chv-coverage-request-mutation";
import { useLiveChvCoverageRequestForWardQuery } from "@/queries/use-live-chv-coverage-request-for-ward-query";

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

function formatDateOnly(value: string | null | undefined) {
  if (!value) {
    return "Unavailable";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "Invalid date";
  }

  return date.toLocaleDateString([], {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

function formatClimateValidRange(climate: ClimateEvidence | null) {
  if (!climate?.valid_date) {
    return "Unavailable";
  }

  const endDate = new Date(climate.valid_date);
  if (Number.isNaN(endDate.getTime())) {
    return "Invalid date";
  }

  const leadDay = climate.lead_day ?? climate.forecast_horizon_days;
  if (typeof leadDay === "number" && leadDay > 1) {
    const startDate = new Date(endDate);
    startDate.setDate(endDate.getDate() - leadDay + 1);
    return `${startDate.toLocaleDateString([], { day: "2-digit", month: "short" })} - ${endDate.toLocaleDateString([], { day: "2-digit", month: "short", year: "numeric" })}`;
  }

  return formatDateOnly(climate.valid_date);
}

function formatLeadDays(days: number[] | undefined) {
  if (!days?.length) {
    return "None";
  }
  if (days.length <= 8) {
    return days.join(", ");
  }
  return `${days.slice(0, 8).join(", ")} +${days.length - 8} more`;
}

function getClimateTone(climate: ClimateEvidence | null) {
  if (!climate) return "default" as const;
  if (climate.fallback_static_rainfall_used || climate.forecast_missing_lead_days.length > 0) {
    return "warning" as const;
  }
  return climate.claimed_lead_time_climate_coverage_sufficient ? ("success" as const) : ("warning" as const);
}

function formatClimateStatus(value: string | undefined) {
  if (!value) return "Coverage unavailable";
  return value
    .toLowerCase()
    .split(/[\s_-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
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

function getToneSurface(tone: "red" | "amber" | "orange" | "blue" | "slate") {
  switch (tone) {
    case "red":
      return "border border-[color-mix(in_srgb,var(--danger)_26%,var(--dashboard-panel-border))] bg-[color-mix(in_srgb,var(--danger)_12%,var(--dashboard-panel-surface))] text-[color:var(--danger)]";
    case "blue":
      return "border border-[color-mix(in_srgb,var(--brand)_24%,var(--dashboard-panel-border))] bg-[color-mix(in_srgb,var(--brand)_12%,var(--dashboard-panel-surface))] text-brand";
    case "orange":
    case "amber":
      return "border border-[color-mix(in_srgb,var(--warning)_28%,var(--dashboard-panel-border))] bg-[color-mix(in_srgb,var(--warning)_14%,var(--dashboard-panel-surface))] text-[color:var(--warning)]";
    case "slate":
    default:
      return "border border-panel-table-wrap bg-[color-mix(in_srgb,var(--dashboard-table-line)_26%,var(--dashboard-panel-surface))] text-panel-copy";
  }
}

function getLifecycleTone(status: "active" | "monitoring" | "escalated" | "resolved") {
  if (status === "escalated") return "danger" as const;
  if (status === "monitoring") return "warning" as const;
  if (status === "resolved") return "success" as const;
  return "info" as const;
}

function getDecisionStatusLabel(alertStatus: string, lifecycleStatus?: "active" | "monitoring" | "escalated" | "resolved") {
  if (alertStatus === "RETRY_PENDING") {
    return "Awaiting retry";
  }
  if (alertStatus === "FAILED") {
    return "Needs escalation";
  }
  if (alertStatus === "DELIVERED") {
    return "Delivered";
  }
  if (lifecycleStatus === "escalated") {
    return "Needs escalation";
  }
  if (lifecycleStatus === "resolved") {
    return "Resolved";
  }
  if (lifecycleStatus === "monitoring") {
    return "Under review";
  }
  return "Action in progress";
}

function getNextActionReasonLabel(alertStatus: string, fallback?: string) {
  if (alertStatus === "RETRY_PENDING") return "Retry pending";
  if (alertStatus === "FAILED") return "Delivery failed";
  if (alertStatus === "DELIVERED") return "Delivery complete";
  return fallback || "Review needed";
}

function getNextActionAvailabilityLabel(isBlocked: boolean | undefined) {
  return isBlocked ? "SMS not available here" : "Ready in linked workflow";
}

function getNextActionSummary({
  alertStatus,
  isBlocked,
  hasLiveCoverageRequest,
}: {
  alertStatus: string;
  isBlocked: boolean | undefined;
  hasLiveCoverageRequest: boolean;
}) {
  if (alertStatus === "RETRY_PENDING" && isBlocked) {
    return hasLiveCoverageRequest
      ? "Delivery retry is still pending. Continue in the ward workflow and use the linked CHV request for field follow-up."
      : "Delivery retry is still pending. Continue in the ward workflow to decide whether follow-up is needed.";
  }
  if (alertStatus === "FAILED") {
    return "Delivery failed. Use the linked workflow to decide whether escalation or field follow-up is needed.";
  }
  if (alertStatus === "DELIVERED") {
    return "Delivery is recorded. Review the ward workflow only if new risk or field evidence changes the situation.";
  }
  return "Use the linked workflow to continue the safest next step for this alert.";
}

function getTimelineStateLabel(tone: "primary" | "progress" | "success" | "danger" | "warning" | "neutral") {
  if (tone === "success") {
    return { label: "Completed", tone: "success" as const };
  }
  if (tone === "danger" || tone === "warning") {
    return { label: "Needs attention", tone: "warning" as const };
  }
  if (tone === "progress") {
    return { label: "In progress", tone: "info" as const };
  }
  return { label: "Recorded", tone: "default" as const };
}

export default function AlertDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const { currentUser } = useAuth();
  const [timelineFilter, setTimelineFilter] = useState<"all" | "system" | "communication" | "field_activity" | "escalation" | "resolution">("all");
  const [expandedTimelineItemId, setExpandedTimelineItemId] = useState<string | null>("delivery-status");
  const [coverageRequestFeedback, setCoverageRequestFeedback] = useState<string | null>(null);
  const [exportFeedback, setExportFeedback] = useState<string | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);
  const [isExporting, setIsExporting] = useState(false);

  const alertId = useMemo(() => Number(params.id), [params.id]);
  const alertDetailQuery = useAlertDetailQuery({
    alertId,
    enabled: Boolean(currentUser) && Number.isFinite(alertId),
  });
  const createFromAlertMutation = useCreateChvCoverageRequestFromAlertMutation();
  const createCoverageRequestMutation = useCreateChvCoverageRequestMutation();
  const alert = alertDetailQuery.data?.alert ?? null;
  const privacyContext = alert?.privacy_context ?? null;
  const wardDetail = alertDetailQuery.data?.ward_detail ?? null;
  const classification = alertDetailQuery.data?.classification ?? null;
  const riskContext = alertDetailQuery.data?.risk_context ?? null;
  const lifecycle = alertDetailQuery.data?.lifecycle ?? null;
  const delivery = alertDetailQuery.data?.delivery ?? null;
  const deliverySummary = alertDetailQuery.data?.delivery_summary ?? null;
  const messageSource = alertDetailQuery.data?.message_source ?? null;
  const climateEvidence = alertDetailQuery.data?.climate_evidence ?? null;
  const chvResponseSummary = alertDetailQuery.data?.chv_response_summary ?? null;
  const facilityResponseSummary = alertDetailQuery.data?.facility_response_summary ?? null;
  const recommendedNextAction = alertDetailQuery.data?.recommended_next_action ?? null;
  const currentState = alertDetailQuery.data?.current_state ?? [];
  const freshness = alertDetailQuery.data?.freshness ?? null;
  const timeline = alertDetailQuery.data?.timeline ?? [];
  const isLoading = alertDetailQuery.isPending;
  const isRefreshing = alertDetailQuery.isFetching;
  const error =
    alertDetailQuery.error instanceof Error
      ? alertDetailQuery.error.message
      : !isLoading && alertDetailQuery.data && !alertDetailQuery.data.alert
        ? "Alert detail is not available in your current scope."
        : null;
  const filteredTimeline = timeline.filter((item) => timelineFilter === "all" || item.category === timelineFilter);
  const lastUpdatedTimestamp = alertDetailQuery.data?.last_updated_at ?? freshness?.updated_at ?? null;
  const AlertTypeIcon = classification ? getClassificationIcon(classification.icon_key) : ShieldAlert;
  const decisionStatusLabel = alert ? getDecisionStatusLabel(alert.status, lifecycle?.status) : "Decision context unavailable";
  const hasUsefulMessageSource = Boolean(
    messageSource &&
      (messageSource.preview_text ||
        messageSource.trigger_type ||
        messageSource.mode !== "unavailable"),
  );
  const canRequestCoverage = hasActionCapability(currentUser, "manage_chv_operations");
  const canExportReport = canExportSensitiveReports(currentUser);
  const isCoverageRequestPending = createFromAlertMutation.isPending || createCoverageRequestMutation.isPending;
  const liveCoverageRequestQuery = useLiveChvCoverageRequestForWardQuery({
    wardId: alert?.ward ?? null,
    enabled: Boolean(currentUser) && Boolean(alert?.ward),
  });
  const liveCoverageRequest = liveCoverageRequestQuery.data ?? null;
  const coverageRequestActionLabel = liveCoverageRequest
    ? "View CHV coverage request"
    : "Request CHV coverage";
  const coverageRequestPendingLabel = liveCoverageRequest
    ? "Opening CHV coverage request..."
    : "Preparing CHV coverage request...";
  const nextActionSummary = alert
    ? getNextActionSummary({
        alertStatus: alert.status,
        isBlocked: recommendedNextAction?.blocked,
        hasLiveCoverageRequest: Boolean(liveCoverageRequest),
      })
    : "Use the linked workflow to continue alert review.";
  const nextActionFacts = alert
    ? [
        ["Why now", getNextActionReasonLabel(alert.status, lifecycle?.status_label)],
        ["Can this page send it?", getNextActionAvailabilityLabel(recommendedNextAction?.blocked)],
        ["Continue through", liveCoverageRequest ? "Linked CHV request" : "Ward workflow"],
      ]
    : [];

  async function handleAlertReportExport() {
    if (!alert) {
      return;
    }

    setExportFeedback(null);
    setExportError(null);
    setIsExporting(true);

    try {
      const exportRequest = await createSensitiveExportViaBff({
        export_type: "ALERT_DETAIL_REPORT",
        purpose: "Operator requested alert detail report for delivery review.",
        filters: { alert_id: alert.id },
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
      {coverageRequestFeedback ? (
        <StatusBanner tone="success" icon={<CheckCircle2 aria-hidden="true" />}>
          {coverageRequestFeedback}
        </StatusBanner>
      ) : null}
      {exportFeedback ? (
        <StatusBanner tone="info" icon={<ShieldAlert aria-hidden="true" />}>
          {exportFeedback}
        </StatusBanner>
      ) : null}
      {privacyContext ? (
        <StatusBanner tone={privacyContext.redacted ? "info" : "warning"} icon={<ShieldAlert aria-hidden="true" />}>
          {privacyContext.redacted
            ? `Sensitive contact details are redacted for this view. ${privacyContext.reason}`
            : `Sensitive contact details are visible in this view. ${privacyContext.reason}`}
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
              {alert && lifecycle ? (
                <StatusBadge tone={getLifecycleTone(lifecycle.status)} className="rounded-full px-3 py-1.5 tracking-[0.14em]">
                  {lifecycle.status_label}
                </StatusBadge>
              ) : null}
            </div>
            <p className="max-w-3xl text-sm text-panel-muted">
              Alert lifecycle, linked ward feedback, and the available operational response path for this alert.
            </p>
          </div>

          {alert && canExportReport ? (
            <Button
              variant="secondary"
              className="px-4"
              onClick={() => {
                void handleAlertReportExport();
              }}
              disabled={isExporting}
            >
              <Download className="size-4" aria-hidden="true" />
              <span>{isExporting ? "Requesting Export" : "Export Report"}</span>
            </Button>
          ) : null}
        </div>
      </section>

      {isLoading ? (
        <StatusBanner tone="info" icon={<ShieldAlert aria-hidden="true" />}>
          Loading alert detail...
        </StatusBanner>
      ) : null}

      {!isLoading && !error && alert ? (
        <>
          <Card className="rounded-[2rem] border-[color:var(--warning)]/20 bg-[color-mix(in_srgb,var(--warning)_6%,var(--panel))] px-5 py-5 sm:px-6">
            <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
              <div className="max-w-4xl space-y-4">
                <div className="space-y-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="inline-flex items-center gap-2 rounded-full border border-[color:var(--warning)]/25 px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em] text-[color:var(--warning)]">
                      <AlertTriangle className="size-3.5" aria-hidden="true" />
                      Next action
                    </span>
                    {recommendedNextAction?.blocked ? (
                      <StatusBadge tone="warning" className="rounded-full px-2.5 py-1 tracking-[0.12em]">
                        Handoff required
                      </StatusBadge>
                    ) : null}
                  </div>
                  <div className="space-y-2">
                    <h2 className="text-[clamp(1.55rem,1.2rem+1vw,2rem)] font-semibold leading-tight text-panel-strong">
                      {recommendedNextAction?.label ?? "Continue alert review"}
                    </h2>
                    <p className="max-w-3xl text-sm leading-6 text-panel-copy">{nextActionSummary}</p>
                  </div>
                </div>

                <div className="grid gap-3 sm:grid-cols-3">
                  {nextActionFacts.map(([label, value]) => (
                    <div
                      key={label}
                      className="rounded-xl border border-[var(--dashboard-table-line)] bg-[color-mix(in_srgb,var(--dashboard-table-line)_14%,transparent)] px-3 py-3"
                    >
                      <p className="text-[0.68rem] font-semibold uppercase tracking-[0.14em] text-panel-subtle">{label}</p>
                      <p className="mt-1 text-sm font-semibold text-panel-strong">{value}</p>
                    </div>
                  ))}
                </div>

                <details className="group max-w-3xl rounded-xl border border-[var(--dashboard-table-line)] bg-[color-mix(in_srgb,var(--dashboard-table-line)_10%,transparent)] px-4 py-3">
                  <summary className="flex cursor-pointer list-none items-center justify-between gap-3 text-sm font-semibold text-panel-copy">
                    <span>Why this action?</span>
                    <ChevronRight className="size-4 shrink-0 transition group-open:rotate-90" aria-hidden="true" />
                  </summary>
                  <div className="mt-3 grid gap-3 text-sm leading-6 text-panel-muted md:grid-cols-2">
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-[0.14em] text-panel-subtle">Reason</p>
                      <p className="mt-1 text-panel-copy">
                        {recommendedNextAction?.detail ?? "Use the linked ward workflow to continue review."}
                      </p>
                    </div>
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-[0.14em] text-panel-subtle">Limit</p>
                      <p className="mt-1 text-panel-copy">
                        {recommendedNextAction?.blocked_reason ??
                          "This page surfaces the next step, but execution continues through the linked ward and alerts workflow."}
                      </p>
                    </div>
                  </div>
                </details>
              </div>

              <div className="flex shrink-0 flex-col gap-3 lg:items-end">
                <Link
                  href={`/wards/${alert.ward}`}
                  className="inline-flex h-11 items-center justify-center gap-2 rounded-pill bg-[var(--login-submit-start)] px-4 text-sm font-semibold text-white shadow-[var(--login-submit-shadow)] transition hover:bg-[var(--login-submit-end)] hover:shadow-[var(--login-submit-shadow-hover)]"
                >
                  <Share2 className="size-4" aria-hidden="true" />
                  <span>Continue in ward workflow</span>
                </Link>
                {canRequestCoverage && (alert.public_id || liveCoverageRequest) ? (
                  <Button
                    onClick={async () => {
                      setCoverageRequestFeedback(null);

                       if (liveCoverageRequest) {
                        router.push(`/chvs/requests/${liveCoverageRequest.public_id}`);
                        return;
                      }

                      try {
                        const handoff = await createFromAlertMutation.mutateAsync({
                          alert_public_ids: [alert.public_id],
                        });

                        if (handoff.mode === "EXISTING_LIVE_REQUEST" && handoff.existing_request) {
                          setCoverageRequestFeedback("A live CHV coverage request already exists for this ward.");
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
                        router.push(`/chvs/requests/${createdRequest.public_id}`);
                      } catch {
                        // Error banners already reflect the failing mutation.
                      }
                    }}
                    disabled={isCoverageRequestPending}
                    className="px-4"
                  >
                    <ShieldAlert className="size-4" aria-hidden="true" />
                    <span>
                      {isCoverageRequestPending ? coverageRequestPendingLabel : coverageRequestActionLabel}
                    </span>
                  </Button>
                ) : null}
                {canRequestCoverage && liveCoverageRequest ? (
                  <span className="inline-flex rounded-full border border-[var(--dashboard-table-line)] px-3 py-1 text-xs font-semibold uppercase tracking-[0.12em] text-panel-muted">
                    CHV request already linked
                  </span>
                ) : null}
                <span className="max-w-xs text-right text-xs leading-5 text-panel-muted">
                  Other actions unlock after workflow handoff.
                </span>
              </div>
            </div>
          </Card>

          <section className="grid gap-5 xl:grid-cols-[minmax(0,1.35fr)_22rem]">
          <div className="space-y-5">
            <Card className="rounded-[2rem] px-5 py-5 sm:px-6">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <h2 className="text-2xl font-semibold text-panel-strong">Alert Workflow Summary</h2>
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
                  <span className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-subtle">Lifecycle status</span>
                  <strong className="block text-base text-panel-strong">{lifecycle?.status_label ?? "Unknown"}</strong>
                  <small className="text-sm text-panel-muted">{lifecycle?.summary ?? "No lifecycle summary available."}</small>
                </div>
                <div className="space-y-2">
                  <span className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-subtle">Recorded risk</span>
                  <strong className="block text-base text-panel-strong">{riskContext?.level_label ?? "Risk unavailable"}</strong>
                  <small className="text-sm text-panel-muted">{riskContext?.trend_label ?? "Unknown trend"}</small>
                </div>
                <div className="space-y-2">
                  <span className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-subtle">Triggered time</span>
                  <strong className="block text-base text-panel-strong">{formatTimeStamp(alert.created_at)}</strong>
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
                    {classification?.mode === "derived_from_record_text" ? "Derived from alert text" : "Recorded signal"}
                  </StatusBadge>
                </div>
                <div className="space-y-2">
                  <span className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-subtle">Recorded source</span>
                  <strong className="block text-base text-panel-strong">{classification?.trigger_source ?? "Not recorded"}</strong>
                </div>
                <div className="space-y-2">
                  <span className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-subtle">Last updated</span>
                  <strong className="block text-base text-panel-strong">{formatTimeStamp(lastUpdatedTimestamp)}</strong>
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
                        "border border-[color-mix(in_srgb,var(--success)_28%,var(--dashboard-panel-border))] bg-[color-mix(in_srgb,var(--success)_10%,var(--dashboard-panel-surface))] text-[color:var(--success)]",
                      item.tone === "warning" &&
                        "border border-[color-mix(in_srgb,var(--warning)_30%,var(--dashboard-panel-border))] bg-[color-mix(in_srgb,var(--warning)_12%,var(--dashboard-panel-surface))] text-[color:var(--warning)]",
                      item.tone === "neutral" &&
                        "border border-panel-table-wrap bg-[color-mix(in_srgb,var(--dashboard-table-line)_26%,var(--dashboard-panel-surface))] text-panel-copy",
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
                  <h2 className="text-2xl font-semibold text-panel-strong">Climate Source Evidence</h2>
                  <p className="mt-2 text-sm text-panel-muted">
                    {climateEvidence?.observed_vs_forecast_source_label ?? "Climate source unavailable"}
                  </p>
                </div>
                <StatusBadge tone={getClimateTone(climateEvidence)} className="w-max px-3 py-1.5 tracking-[0.14em]">
                  {formatClimateStatus(climateEvidence?.climate_coverage_status)}
                </StatusBadge>
              </div>

              <div className="mt-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                {[
                  ["Source label", climateEvidence?.observed_vs_forecast_source_label ?? "Unavailable"],
                  ["Provider", climateEvidence?.source_provider || "Unavailable"],
                  ["Issue time", formatTimeStamp(climateEvidence?.issue_time ?? null)],
                  ["Valid dates", formatClimateValidRange(climateEvidence)],
                  [
                    "Forecast coverage",
                    `${climateEvidence?.forecast_coverage_days ?? 0}/${climateEvidence?.claimed_forecast_horizon_days ?? 14} days`,
                  ],
                  ["Missing lead days", formatLeadDays(climateEvidence?.forecast_missing_lead_days)],
                ].map(([label, value]) => (
                  <div key={label} className="rounded-[1.2rem] border border-panel-table-wrap px-4 py-3">
                    <p className="text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle">{label}</p>
                    <p className="mt-2 text-sm font-semibold text-panel-strong">{value}</p>
                  </div>
                ))}
              </div>

              {climateEvidence?.fallback_static_rainfall_used ? (
                <div className="mt-5 flex items-start gap-2 rounded-[1.2rem] border border-[color-mix(in_srgb,var(--warning)_20%,var(--dashboard-table-line))] bg-[color-mix(in_srgb,var(--warning)_8%,var(--panel))] px-4 py-3">
                  <AlertTriangle className="mt-0.5 size-4 shrink-0 text-[color:var(--warning)]" aria-hidden="true" />
                  <p className="text-sm leading-6 text-panel-copy">
                    Fallback source warning: static rainfall is present and is not live forecast evidence.
                  </p>
                </div>
              ) : null}

              {climateEvidence?.forecast_missing_lead_days?.length ? (
                <div className="mt-5 flex items-start gap-2 rounded-[1.2rem] border border-[color-mix(in_srgb,var(--warning)_20%,var(--dashboard-table-line))] bg-[color-mix(in_srgb,var(--warning)_8%,var(--panel))] px-4 py-3">
                  <AlertTriangle className="mt-0.5 size-4 shrink-0 text-[color:var(--warning)]" aria-hidden="true" />
                  <p className="text-sm leading-6 text-panel-copy">
                    Missing forecast lead days: {formatLeadDays(climateEvidence.forecast_missing_lead_days)}.
                  </p>
                </div>
              ) : null}
            </Card>

            <Card className="rounded-[2rem] px-5 py-5 sm:px-6">
              <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                <div>
                  <h2 className="text-2xl font-semibold text-panel-strong">Operational Timeline</h2>
                  <p className="mt-2 text-sm text-panel-muted">
                    Alert creation, communication, field feedback, escalation, and resolution signals visible on this record.
                  </p>
                </div>
                <StatusBadge tone={getLifecycleTone(lifecycle?.status ?? "active")} className="px-3 py-1.5 tracking-[0.14em]">
                  {lifecycle?.status_label ?? "Lifecycle unavailable"}
                </StatusBadge>
              </div>

              <div className="mt-6 grid gap-4 md:grid-cols-4">
                <Card className="rounded-[1.4rem] bg-[color-mix(in_srgb,var(--dashboard-table-line)_18%,transparent)] px-4 py-4 shadow-none">
                  <p className="text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle">Recipient count</p>
                  <p className="mt-2 text-2xl font-semibold tracking-[-0.04em] text-panel-strong">
                    {deliverySummary?.recipient_count ?? 1}
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
                  <p className="text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle">Field signals</p>
                  <p className="mt-2 text-lg font-semibold tracking-[-0.04em] text-panel-strong">
                    {chvResponseSummary?.response_count ?? 0}
                  </p>
                </Card>
              </div>

              <div className="mt-6 flex flex-wrap gap-2">
                {[
                  { value: "all", label: "All" },
                  { value: "communication", label: "Communication" },
                  { value: "field_activity", label: "Field activity" },
                  { value: "escalation", label: "Escalation" },
                  { value: "resolution", label: "Resolution" },
                  { value: "system", label: "System" },
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
                    onClick={() =>
                      setTimelineFilter(
                        filter.value as "all" | "system" | "communication" | "field_activity" | "escalation" | "resolution",
                      )
                    }
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
                          item.tone === "primary" && "border border-[color-mix(in_srgb,var(--brand)_24%,var(--dashboard-panel-border))] bg-[color-mix(in_srgb,var(--brand)_12%,var(--dashboard-panel-surface))] text-brand",
                          item.tone === "progress" && "border border-[color-mix(in_srgb,var(--warning)_28%,var(--dashboard-panel-border))] bg-[color-mix(in_srgb,var(--warning)_12%,var(--dashboard-panel-surface))] text-[color:var(--warning)]",
                          item.tone === "success" && "border border-[color-mix(in_srgb,var(--success)_26%,var(--dashboard-panel-border))] bg-[color-mix(in_srgb,var(--success)_12%,var(--dashboard-panel-surface))] text-[color:var(--success)]",
                          item.tone === "danger" && "border border-[color-mix(in_srgb,var(--danger)_26%,var(--dashboard-panel-border))] bg-[color-mix(in_srgb,var(--danger)_12%,var(--dashboard-panel-surface))] text-[color:var(--danger)]",
                          item.tone === "warning" && "border border-[color-mix(in_srgb,var(--warning)_30%,var(--dashboard-panel-border))] bg-[color-mix(in_srgb,var(--warning)_14%,var(--dashboard-panel-surface))] text-[color:var(--warning)]",
                          item.tone === "neutral" && "border border-panel-table-wrap bg-[color-mix(in_srgb,var(--dashboard-table-line)_26%,var(--dashboard-panel-surface))] text-panel-copy",
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
                          <div>
                            <div className="flex flex-wrap items-center gap-2">
                              <strong className="text-base text-panel-strong">{item.title}</strong>
                              <StatusBadge tone={getTimelineStateLabel(item.tone).tone} className="tracking-[0.12em]">
                                {getTimelineStateLabel(item.tone).label}
                              </StatusBadge>
                            </div>
                            {(item.actor || item.event_type) ? (
                              <p className="mt-1 text-xs font-semibold uppercase tracking-[0.14em] text-panel-subtle">
                                {[item.actor, item.event_type].filter(Boolean).join(" • ")}
                              </p>
                            ) : null}
                          </div>
                          <span className="shrink-0 text-xs font-semibold uppercase tracking-[0.14em] text-panel-subtle">
                            {formatTimeOnly(item.timestamp)}
                          </span>
                        </div>
                        <p className="mt-2 text-sm leading-6 text-panel-copy">{item.description}</p>
                        {item.message ? <small className="mt-2 block text-sm text-panel-muted">{item.message}</small> : null}
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
              <h2 className="text-2xl font-semibold text-panel-strong">Decision Context</h2>

              <div className="mt-5 space-y-5">
                <div className="space-y-1">
                  <span className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-subtle">Delivery state</span>
                  <strong className="block text-base text-panel-strong">
                    {decisionStatusLabel}
                  </strong>
                </div>
                <div className="space-y-1">
                  <span className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-subtle">Current risk direction</span>
                  <strong className="block text-base leading-6 text-panel-strong">
                    {riskContext?.trend_label ?? "No risk direction recorded"}
                  </strong>
                  <p className="text-sm text-panel-muted">{lifecycle?.summary ?? "Use the linked ward workflow for the current operational summary."}</p>
                </div>
                <div className="space-y-1">
                  <span className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-subtle">Response coverage</span>
                  <strong className="block text-base text-panel-strong">
                    {chvResponseSummary?.coverage_label ?? "No response coverage available"}
                  </strong>
                  <p className="text-sm text-panel-muted">{chvResponseSummary?.summary ?? "No CHV response summary is available."}</p>
                </div>
                <div className="space-y-1">
                  <span className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-subtle">Facility pressure signal</span>
                  <strong className="block text-base text-panel-strong">
                    {facilityResponseSummary?.status_label ?? "No facility signal available"}
                  </strong>
                  <p className="text-sm text-panel-muted">{facilityResponseSummary?.summary ?? "No facility response summary is available."}</p>
                </div>
                <div className="space-y-1">
                  <span className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-subtle">Action handoff</span>
                  <strong className="block text-base text-panel-strong">
                    Continue in linked ward workflow
                  </strong>
                  <p className="text-sm text-panel-muted">
                    {recommendedNextAction?.blocked_reason ?? "This record still routes through ward and alerts workflow steps."}
                  </p>
                </div>
              </div>

              <div className="mt-6">
                <StatusBanner tone="warning" icon={<ShieldAlert aria-hidden="true" />}>
                  This page surfaces the next move, but execution still happens through the linked ward and alerts workflow.
                </StatusBanner>
              </div>
            </Card>

            <Card className="rounded-[2rem] px-5 py-5">
              <div className="flex items-start justify-between gap-4">
                <h2 className="text-2xl font-semibold text-panel-strong">Delivery Summary</h2>
              </div>

              <dl className="mt-6 space-y-4 border-t border-panel-table-wrap pt-5 text-sm">
                {[
                  ["Channel", deliverySummary?.channel_label ?? alert.channel],
                  ["Audience", deliverySummary?.audience_label ?? "Recorded recipient"],
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

            {hasUsefulMessageSource ? (
              <Card className="rounded-[2rem] px-5 py-5">
                <div className="flex items-start justify-between gap-4">
                  <h2 className="text-2xl font-semibold text-panel-strong">Message Source</h2>
                </div>

                <div className="mt-6 space-y-4">
                  <div className="flex flex-wrap items-center gap-3">
                    <strong className="text-base text-panel-strong">{messageSource?.label ?? "Recorded source"}</strong>
                    <StatusBadge
                      tone={
                        messageSource?.mode === "operator_edited"
                          ? "warning"
                          : messageSource?.mode === "backend_generated"
                            ? "info"
                            : "default"
                      }
                      className="tracking-[0.12em]"
                    >
                      {messageSource?.mode === "operator_edited"
                        ? "Operator adjusted"
                        : messageSource?.mode === "backend_generated"
                          ? "System draft used"
                          : "Metadata recorded"}
                    </StatusBadge>
                  </div>

                  <p className="text-sm text-panel-muted">
                    {messageSource?.summary ?? "Message-source detail is recorded for this alert."}
                  </p>

                  {messageSource?.preview_text ? (
                    <div className="rounded-[1.2rem] border border-panel-table-wrap bg-[color-mix(in_srgb,var(--dashboard-table-line)_18%,transparent)] px-4 py-4">
                      <p className="text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle">Recorded message</p>
                      <p className="mt-2 text-sm leading-6 text-panel-copy">{messageSource.preview_text}</p>
                    </div>
                  ) : null}

                  {messageSource?.trigger_type ? (
                    <p className="text-xs text-panel-muted">
                      Guided action recorded at queue time: {messageSource.trigger_type.replaceAll("_", " ").toLowerCase()}.
                    </p>
                  ) : null}
                </div>
              </Card>
            ) : null}

            <Card className="rounded-[2rem] overflow-hidden p-0">
              <div className="relative h-40 bg-[radial-gradient(circle_at_top_left,color-mix(in_srgb,var(--brand)_12%,var(--dashboard-panel-surface)),transparent_45%),linear-gradient(135deg,color-mix(in_srgb,var(--dashboard-table-line)_18%,var(--dashboard-panel-surface)),var(--dashboard-panel-surface))]">
                <div className="absolute inset-0 bg-[linear-gradient(90deg,color-mix(in_srgb,var(--dashboard-table-line)_28%,transparent)_1px,transparent_1px),linear-gradient(color-mix(in_srgb,var(--dashboard-table-line)_28%,transparent)_1px,transparent_1px)] bg-[size:3.5rem_3.5rem] opacity-60" />
                <div className="absolute inset-x-6 bottom-5">
                  <div className="inline-flex rounded-full bg-panel/90 px-4 py-2 text-xs font-semibold uppercase tracking-[0.16em] text-panel-strong shadow-sm backdrop-blur">
                    Ward risk data
                  </div>
                </div>
              </div>

              <div className="space-y-4 px-5 py-5">
                <h3 className="text-xl font-semibold text-panel-strong">Ward Context</h3>
                <p className="text-sm leading-6 text-panel-copy">
                  {wardDetail
                    ? `${wardDetail.name} is the linked ward summary for this alert and shows ${wardDetail.current_risk_level.toLowerCase()} recorded ward risk.`
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
          </div>
          </section>
        </>
      ) : null}
    </div>
  );
}
