"use client";

import {
  AlertTriangle,
  ArrowLeft,
  ArrowUpRight,
  Bell,
  CheckCircle2,
  ChevronRight,
  Clock3,
  Droplets,
  History,
  MapPinned,
  Minus,
  ShieldAlert,
  Waves,
  Zap,
} from "lucide-react";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { useMemo } from "react";

import { useAuth } from "@/components/auth-provider";
import { DashboardTopbar } from "@/components/dashboard-topbar";
import { MigoriWardMap } from "@/components/migori-ward-map";
import { TriggerAlertPanel } from "@/components/trigger-alert-panel";
import { Card } from "@/components/ui/card";
import { StatusBadge } from "@/components/ui/status-badge";
import { cn } from "@/lib/cn";
import type { AlertRecord, RiskScoreRecord, WardIntelligenceDriverItem } from "@/lib/dashboard";
import { canTriggerAlerts } from "@/lib/roles";
import { type WardDetailState, useWardDetailQuery } from "@/queries/use-ward-detail-query";

function normalizeRiskScore(score: number | null) {
  if (typeof score !== "number" || !Number.isFinite(score)) {
    return 0;
  }
  if (score <= 1) {
    return Math.max(0, Math.min(score * 100, 100));
  }
  return Math.max(0, Math.min(score, 100));
}

function formatRiskScore(score: number | null) {
  if (typeof score !== "number" || !Number.isFinite(score)) {
    return "N/A";
  }
  return `${Math.round(normalizeRiskScore(score))}/100`;
}

function formatRelativeMinutes(timestamp: string | null) {
  if (!timestamp) return "Unavailable";

  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return "Invalid timestamp";

  const diffMinutes = Math.max(0, Math.round((Date.now() - date.getTime()) / 60000));
  if (diffMinutes < 1) return "Just now";
  if (diffMinutes === 1) return "1 min ago";
  if (diffMinutes < 60) return `${diffMinutes} min ago`;

  const diffHours = Math.round(diffMinutes / 60);
  if (diffHours === 1) return "1 hr ago";
  if (diffHours < 24) return `${diffHours} hr ago`;

  const diffDays = Math.round(diffHours / 24);
  return `${diffDays} d ago`;
}

function formatOperationalTime(timestamp: string | null) {
  if (!timestamp) return "Unavailable";

  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return "Invalid timestamp";

  return `${date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })} (${formatRelativeMinutes(timestamp)})`;
}

function formatRiskLevel(riskLevel: WardDetailState["riskLevel"]) {
  switch (riskLevel) {
    case "HIGH":
      return "High risk";
    case "MEDIUM":
      return "Medium risk";
    case "LOW":
      return "Low risk";
    default:
      return "Unknown risk";
  }
}

function toTitleCase(value: string) {
  return value
    .toLowerCase()
    .split(/[\s_-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function getAlertHeadline(alert: AlertRecord) {
  if (alert.message && alert.message.trim().length > 0) {
    return alert.message.trim();
  }
  return `${toTitleCase(alert.channel)} alert`;
}

function getRiskDriverIcon(driver: WardIntelligenceDriverItem) {
  switch (driver.source_field) {
    case "rainfall_mm":
      return <Droplets className="size-4" aria-hidden="true" />;
    case "flood_indicator":
      return <Waves className="size-4" aria-hidden="true" />;
    case "predicted_cases":
      return <History className="size-4" aria-hidden="true" />;
    case "model_run.status":
    default:
      return <Clock3 className="size-4" aria-hidden="true" />;
  }
}

function getSafeReturnTo(value: string | null) {
  if (!value) {
    return "/wards";
  }
  return value.startsWith("/wards") ? value : "/wards";
}

function getHistoryTrendIcon(index: number, history: RiskScoreRecord[]) {
  const current = history[index];
  const previous = history[index + 1];

  if (!current || !previous) return "flat" as const;
  if (normalizeRiskScore(current.score) > normalizeRiskScore(previous.score)) return "up" as const;
  if (normalizeRiskScore(current.score) < normalizeRiskScore(previous.score)) return "down" as const;
  return "flat" as const;
}

function getRiskBadgeTone(level: WardDetailState["riskLevel"]) {
  if (level === "HIGH") return "danger" as const;
  if (level === "MEDIUM") return "warning" as const;
  if (level === "LOW") return "success" as const;
  return "default" as const;
}

function getTriggerTone(triggerState: WardDetailState["triggerState"]) {
  if (triggerState === "ACTION_IN_PROGRESS" || triggerState === "REVIEW_PENDING") return "warning" as const;
  if (triggerState === "TRIGGER_ACTIVE" || triggerState === "RESOLVED") return "success" as const;
  return "default" as const;
}

function formatTriggerState(triggerState: WardDetailState["triggerState"]) {
  if (triggerState === "NONE") return "No active trigger";
  if (triggerState === "TRIGGER_ACTIVE") return "Trigger active";
  if (triggerState === "REVIEW_PENDING") return "Awaiting review";
  if (triggerState === "ACTION_IN_PROGRESS") return "Action in progress";
  return toTitleCase(triggerState);
}

function getRecommendedActionState(detail: WardDetailState) {
  const hasRecentAlerts = detail.relatedAlerts.length > 0 || (detail.workflow?.active_alert_count ?? 0) > 0;
  if (detail.triggerState === "NONE") {
    return {
      primaryAction: "Review alert history",
      why: hasRecentAlerts
        ? "No active trigger is present, but this ward has recent alerts."
        : "No active trigger is present and the latest ward record remains in routine monitoring.",
      nextSteps: hasRecentAlerts
        ? ["Review full alert history", "Continue routine surveillance", "Open trigger flow only if conditions change"]
        : ["Continue routine surveillance", "Review full alert history", "Open trigger flow only if conditions change"],
    };
  }

  return {
    primaryAction: detail.workflow?.recommended_action ?? detail.decisionSummary.headline,
    why: detail.decisionSummary.why,
    nextSteps: detail.decisionSummary.next_steps,
  };
}

function getDecisionCheckpointCopy(detail: WardDetailState | null) {
  if (!detail) {
    return {
      headline: "Decision summary not available yet.",
      why: "Use recent alerts and freshness status to guide review.",
      context: "Context: Ward monitoring view",
    };
  }

  if (detail.triggerState === "NONE" && !detail.actionRequired) {
    return {
      headline: "No decision required at this time.",
      why: "This ward is under routine monitoring.",
      context: "Context: Routine monitoring (no active escalation)",
    };
  }

  return {
    headline: detail.decisionSummary.headline,
    why: detail.decisionSummary.why,
    context: "Context: Active ward decision checkpoint",
  };
}

function getFreshnessTone(isStale: boolean) {
  return isStale ? ("warning" as const) : ("success" as const);
}

function getAlertTone(alert: AlertRecord) {
  if (alert.status === "DELIVERED") return "success" as const;
  if (alert.status === "FAILED") return "danger" as const;
  return "warning" as const;
}

function getAlertSummary(alert: AlertRecord) {
  const parts = [
    `Via ${toTitleCase(alert.channel)}`,
    toTitleCase(alert.status),
  ];

  if (typeof alert.risk_score === "number") {
    parts.push(`Risk ${Math.round(normalizeRiskScore(alert.risk_score))}/100`);
  }

  return parts.join(" • ");
}

function LoadingBlocks({ count = 3, className = "h-16 rounded-[1.25rem] bg-[color-mix(in_srgb,var(--dashboard-table-line)_55%,transparent)]" }) {
  return (
    <div className="space-y-3" aria-hidden="true">
      {Array.from({ length: count }, (_, index) => (
        <div key={index} className={className} />
      ))}
    </div>
  );
}

export default function WardDetailPage() {
  const params = useParams<{ id: string }>();
  const searchParams = useSearchParams();
  const { currentUser } = useAuth();
  const wardId = useMemo(() => Number(params.id), [params.id]);
  const returnTo = useMemo(() => getSafeReturnTo(searchParams.get("returnTo")), [searchParams]);
  const wardDetailQuery = useWardDetailQuery({
    wardId,
    enabled: Boolean(currentUser) && Number.isFinite(wardId),
  });
  const detail = wardDetailQuery.data ?? null;
  const isLoading = wardDetailQuery.isPending;
  const isRefreshing = wardDetailQuery.isFetching;
  const error = wardDetailQuery.error instanceof Error ? wardDetailQuery.error.message : null;
  const isStale = detail?.freshness.is_stale ?? true;
  const topbarTimestampLabel = isRefreshing
    ? "Refreshing..."
    : `${formatOperationalTime(detail?.updatedAt ?? null)}${isStale ? " · Stale" : ""}`;
  const trend = detail?.trend ?? {
    label: "No previous run available",
    direction: "flat" as const,
    delta_points: null,
    mode: "derived_from_recent_history",
  };
  const drivers = detail?.driverItems ?? [];
  const recommendations = detail?.guidanceItems ?? [];
  const wardMapFeatures = detail?.wardMapFeature ? [detail.wardMapFeature] : [];
  const canTriggerFromPage = currentUser ? canTriggerAlerts(currentUser.role) : false;
  const hasLowSignalState = Boolean(
    detail &&
      detail.riskLevel === "LOW" &&
      detail.triggerState === "NONE" &&
      !detail.actionRequired &&
      drivers.length === 0 &&
      detail.riskHistory.length === 0,
  );
  const shouldShowTriggerPanelPrimary = Boolean(
    detail &&
      canTriggerFromPage &&
      (detail.primaryCtaKind === "OPEN_TRIGGER_FLOW" || detail.primaryCtaKind === "REVIEW_TRIGGER"),
  );
  const primaryTriggerButtonLabel = detail?.primaryCtaKind === "REVIEW_TRIGGER" ? "Review trigger" : "Open Trigger Flow";
  const primaryTriggerCloseLabel = detail?.primaryCtaKind === "REVIEW_TRIGGER" ? "Close trigger review" : "Close trigger flow";
  const shouldShowAlertHistoryPrimary = !shouldShowTriggerPanelPrimary;
  const shouldShowSecondaryTriggerFlow =
    Boolean(detail) && canTriggerFromPage && detail?.triggerState === "NONE" && detail.primaryCtaKind !== "OPEN_TRIGGER_FLOW";
  const recommendedActionState = detail ? getRecommendedActionState(detail) : null;
  const decisionCheckpointCopy = getDecisionCheckpointCopy(detail);

  if (!currentUser) {
    return null;
  }

  return (
    <div className="space-y-6">
      <DashboardTopbar
        title="Ward Detail"
        subtitle={detail ? `${detail.county} County ward decision console` : "Migori County ward decision console"}
        lastUpdatedLabel={topbarTimestampLabel}
        lastUpdatedTone={isStale ? "stale" : "default"}
        onRefresh={() => {
          void wardDetailQuery.refetch();
        }}
      />

      {error ? (
        <div className="rounded-2xl border border-[color-mix(in_srgb,var(--danger)_20%,white)] bg-[color-mix(in_srgb,var(--danger)_10%,white)] px-4 py-3 text-sm font-medium text-[color:var(--danger)]">
          <AlertTriangle className="mr-2 inline-flex size-4" aria-hidden="true" />
          {error}
        </div>
      ) : null}

      <Card className="space-y-6 overflow-hidden p-6 md:p-7">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="space-y-4">
            <Link
              href={returnTo}
              className="inline-flex items-center gap-2 text-sm font-semibold text-brand transition hover:text-[var(--login-link-hover)]"
            >
              <ArrowLeft className="size-4" aria-hidden="true" />
              Back to wards
            </Link>

            <div className="space-y-3">
              <div className="flex flex-wrap items-center gap-3">
                <h1 className="text-[clamp(2rem,1.2rem+1vw,3rem)] font-semibold tracking-[-0.05em] text-panel-strong">
                  {isLoading ? "Loading ward detail..." : detail?.wardName ?? "Ward detail"}
                </h1>
                {!isLoading ? (
                  <>
                    <StatusBadge
                      tone={getRiskBadgeTone(detail?.riskLevel ?? "UNKNOWN")}
                      className="rounded-full px-3 py-1.5 tracking-[0.14em]"
                    >
                      {formatRiskLevel(detail?.riskLevel ?? "UNKNOWN")}
                    </StatusBadge>
                    <StatusBadge
                      tone={getTriggerTone(detail?.triggerState ?? "NONE")}
                      className="rounded-full px-3 py-1.5 tracking-[0.14em]"
                    >
                      {formatTriggerState(detail?.triggerState ?? "NONE")}
                    </StatusBadge>
                    <StatusBadge
                      tone={getFreshnessTone(detail?.freshness.is_stale ?? true)}
                      className="rounded-full px-3 py-1.5 tracking-[0.14em]"
                    >
                      {detail?.freshness.is_stale ? "Stale data" : "Fresh data"}
                    </StatusBadge>
                  </>
                ) : null}
              </div>

              <p className="text-sm text-panel-muted">
                {isLoading
                  ? "Preparing the latest ward risk context."
                  : detail
                    ? `${detail.subCounty || "Unassigned sub-county"}, ${detail.county} County${detail.wardCode ? ` • ${detail.wardCode}` : ""}`
                    : "Ward-level risk monitoring."}
              </p>

              <div className="max-w-3xl space-y-2">
                <p className="text-lg font-semibold tracking-[-0.02em] text-panel-strong">
                  {isLoading ? "Loading decision summary..." : decisionCheckpointCopy.headline}
                </p>
                <p className="text-sm leading-6 text-panel-muted">
                  {isLoading ? "Checking current trigger state, alert activity, and freshness." : decisionCheckpointCopy.why}
                </p>
                {!isLoading ? <p className="text-xs font-medium uppercase tracking-[0.16em] text-panel-subtle">{decisionCheckpointCopy.context}</p> : null}
              </div>
            </div>
          </div>

          <div className="w-full max-w-md space-y-3 lg:pl-6">
            {detail ? (
              shouldShowTriggerPanelPrimary ? (
                <TriggerAlertPanel
                  buttonLabel={primaryTriggerButtonLabel}
                  closeLabel={primaryTriggerCloseLabel}
                  buttonClassName="inline-flex h-12 w-full items-center justify-center gap-2 rounded-pill bg-[var(--login-submit-start)] px-5 text-base font-semibold text-white shadow-[var(--login-submit-shadow)] transition hover:bg-[var(--login-submit-end)] hover:shadow-[var(--login-submit-shadow-hover)]"
                  fixedWard={{
                    id: detail.wardId,
                    name: detail.wardName,
                    county: detail.county,
                    subCounty: detail.subCounty,
                    riskLevel: detail.riskLevel,
                    riskScore: detail.riskScore,
                    predictedCases: detail.predictedCases,
                    updatedAt: detail.updatedAt,
                  }}
                />
              ) : (
                <div className="flex items-start gap-2 rounded-[1.25rem] border border-[color-mix(in_srgb,var(--warning)_18%,white)] bg-[color-mix(in_srgb,var(--warning)_8%,white)] px-4 py-3 text-sm font-medium text-[color:var(--warning)] dark:border-[color-mix(in_srgb,var(--warning)_24%,var(--panel-border))] dark:bg-[color-mix(in_srgb,var(--warning)_14%,var(--panel))] dark:text-[color-mix(in_srgb,var(--warning)_78%,white)]">
                  <AlertTriangle className="mt-0.5 inline-flex size-4 shrink-0" aria-hidden="true" />
                  <span>
                    {canTriggerFromPage
                      ? "Current next step: review alert history. Open trigger flow only if conditions change."
                      : "Recommended action is visible, but this role cannot start or review trigger work from this page."}
                  </span>
                </div>
              )
            ) : null}

            <div className="grid gap-3 sm:grid-cols-2">
              <Link
                href="/alerts"
                className={cn(
                  "inline-flex h-11 w-full items-center justify-center gap-2 whitespace-nowrap rounded-pill px-5 text-sm font-semibold transition sm:col-span-2",
                  shouldShowAlertHistoryPrimary
                    ? "bg-[var(--login-submit-start)] text-white shadow-[var(--login-submit-shadow)] hover:bg-[var(--login-submit-end)] hover:shadow-[var(--login-submit-shadow-hover)]"
                    : "border border-[var(--dashboard-table-line)] bg-[color-mix(in_srgb,var(--dashboard-table-line)_18%,transparent)] text-panel-strong hover:bg-[color-mix(in_srgb,var(--dashboard-table-line)_34%,transparent)]",
                )}
              >
                View full alert history
                <ChevronRight className="size-4" aria-hidden="true" />
              </Link>

              {shouldShowSecondaryTriggerFlow ? (
                <TriggerAlertPanel
                  buttonLabel="Open trigger flow"
                  closeLabel="Close trigger flow"
                  buttonClassName="inline-flex h-11 w-full items-center justify-center gap-2 rounded-pill border border-[var(--dashboard-table-line)] bg-[color-mix(in_srgb,var(--dashboard-table-line)_18%,transparent)] px-5 text-sm font-semibold text-panel-strong transition hover:bg-[color-mix(in_srgb,var(--dashboard-table-line)_34%,transparent)]"
                  fixedWard={{
                    id: detail.wardId,
                    name: detail.wardName,
                    county: detail.county,
                    subCounty: detail.subCounty,
                    riskLevel: detail.riskLevel,
                    riskScore: detail.riskScore,
                    predictedCases: detail.predictedCases,
                    updatedAt: detail.updatedAt,
                  }}
                />
              ) : null}
            </div>

            <p className="text-xs leading-5 text-panel-muted">
              Trigger review and alert handling may continue in dedicated flows. This page keeps the next truthful step visible without implying all execution completes here.
            </p>
          </div>
        </div>

        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          {[
            ["Risk score", isLoading ? "Loading..." : formatRiskScore(detail?.riskScore ?? null)],
            ["Expected cases", isLoading ? "Loading..." : detail ? String(detail.predictedCases) : "Unavailable"],
            ["Last alert", isLoading ? "Loading..." : detail?.lastAlertAt ? formatRelativeMinutes(detail.lastAlertAt) : "No recent alerts"],
            ["Latest record", isLoading ? "Loading..." : formatOperationalTime(detail?.updatedAt ?? null)],
          ].map(([label, value]) => (
            <div
              key={label}
              className="rounded-[1.5rem] border border-[var(--dashboard-table-line)] bg-[color-mix(in_srgb,var(--dashboard-table-line)_20%,transparent)] px-4 py-4"
            >
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted">{label}</p>
              <p className="mt-2 text-lg font-semibold text-panel-strong">{value}</p>
            </div>
          ))}
        </div>
      </Card>

      <section className="grid items-start gap-6 xl:grid-cols-[minmax(0,1.5fr)_minmax(320px,0.9fr)]">
        <div className="space-y-6">
          <Card className="space-y-5 p-6">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
              <div className="flex items-center gap-3">
                <span className="inline-flex size-11 items-center justify-center rounded-2xl bg-[color-mix(in_srgb,var(--warning)_12%,white)] text-[color:var(--warning)] dark:bg-[color-mix(in_srgb,var(--warning)_20%,transparent)]">
                  <ShieldAlert className="size-5" aria-hidden="true" />
                </span>
                <div className="space-y-1">
                  <h3 className="text-xl font-semibold tracking-[-0.03em] text-panel-strong">
                    {hasLowSignalState ? "Risk signals & trend" : "Observed signals"}
                  </h3>
                  <p className="text-sm text-panel-muted">
                    {hasLowSignalState ? "Single low-signal checkpoint for this ward." : "Live facts from the latest ward records."}
                  </p>
                </div>
              </div>
              <div
                className={cn(
                  "inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm font-semibold",
                  trend.direction === "up"
                    ? "bg-[color-mix(in_srgb,var(--danger)_10%,white)] text-[color:var(--danger)]"
                    : trend.direction === "down"
                      ? "bg-[color-mix(in_srgb,var(--success)_10%,white)] text-[color:var(--success)]"
                      : "bg-[color-mix(in_srgb,var(--dashboard-table-line)_40%,transparent)] text-panel-copy",
                )}
              >
                <ArrowUpRight className={cn("size-4", trend.direction === "down" && "rotate-90")} aria-hidden="true" />
                <span>{isLoading ? "Loading trend..." : trend.label}</span>
              </div>
            </div>

            {isLoading ? (
              <LoadingBlocks count={3} />
            ) : hasLowSignalState ? (
              <div className="rounded-[1.5rem] border border-dashed border-[var(--dashboard-table-line)] bg-[color-mix(in_srgb,var(--dashboard-table-line)_16%,transparent)] px-4 py-4">
                <p className="text-sm font-semibold text-panel-strong">No active signals or trends detected.</p>
                <p className="mt-1 text-sm text-panel-muted">This ward is currently under routine monitoring.</p>
                <p className="mt-1 text-sm text-panel-muted">
                  Latest record: {detail?.updatedAt ? formatOperationalTime(detail.updatedAt) : "Unavailable"}
                </p>
              </div>
            ) : drivers.length > 0 ? (
              <div className="space-y-3">
                {drivers.map((driver) => (
                  <article
                    key={driver.text}
                    className="flex items-center gap-3 rounded-[1.5rem] border border-[var(--dashboard-table-line)] bg-[color-mix(in_srgb,var(--dashboard-table-line)_28%,transparent)] px-4 py-4"
                  >
                    <span
                      className={cn(
                        "size-3 rounded-full",
                        driver.tone === "critical"
                          ? "bg-[color:var(--danger)]"
                          : driver.tone === "warning"
                            ? "bg-[color:var(--warning)]"
                            : "bg-[color:var(--success)]",
                      )}
                      aria-hidden="true"
                    />
                    <span
                      className={cn(
                        "inline-flex size-9 items-center justify-center rounded-full",
                        driver.tone === "critical"
                          ? "bg-[color-mix(in_srgb,var(--danger)_10%,white)] text-[color:var(--danger)] dark:bg-[color-mix(in_srgb,var(--danger)_18%,transparent)]"
                          : driver.tone === "warning"
                            ? "bg-[color-mix(in_srgb,var(--warning)_10%,white)] text-[color:var(--warning)] dark:bg-[color-mix(in_srgb,var(--warning)_18%,transparent)]"
                            : "bg-[color-mix(in_srgb,var(--dashboard-table-line)_40%,transparent)] text-panel-copy",
                      )}
                    >
                      {getRiskDriverIcon(driver)}
                    </span>
                    <strong className="text-sm font-semibold text-panel-strong">{driver.text}</strong>
                  </article>
                ))}
              </div>
            ) : (
              <div className="rounded-[1.5rem] border border-dashed border-[var(--dashboard-table-line)] bg-[color-mix(in_srgb,var(--dashboard-table-line)_16%,transparent)] px-4 py-4">
                <p className="text-sm font-semibold text-panel-strong">No active risk drivers recorded.</p>
                <p className="mt-1 text-sm text-panel-muted">
                  Driver summaries will appear when model runs include explainable signals.
                </p>
                <p className="mt-1 text-sm text-panel-muted">
                  Latest record: {detail?.updatedAt ? formatOperationalTime(detail.updatedAt) : "Unavailable"}
                </p>
              </div>
            )}
          </Card>

          {!hasLowSignalState ? (
            <Card className="space-y-5 p-6">
              <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                <div className="flex items-center gap-3">
                  <span className="inline-flex size-11 items-center justify-center rounded-2xl bg-[color-mix(in_srgb,var(--dashboard-sidebar-title)_12%,white)] text-brand dark:bg-[color-mix(in_srgb,var(--dashboard-sidebar-title)_20%,transparent)]">
                    <Waves className="size-5" aria-hidden="true" />
                  </span>
                  <div className="space-y-1">
                    <h3 className="text-xl font-semibold tracking-[-0.03em] text-panel-strong">Risk history</h3>
                    <p className="text-sm text-panel-muted">Compact record of recent ward runs.</p>
                  </div>
                </div>
              </div>

              {isLoading ? (
                <LoadingBlocks count={4} className="h-14 rounded-[1.25rem] bg-[color-mix(in_srgb,var(--dashboard-table-line)_55%,transparent)]" />
              ) : detail && detail.riskHistory.length > 0 ? (
                <div className="overflow-hidden rounded-[1.5rem] border border-[var(--dashboard-table-line)]">
                  <div className="overflow-x-auto">
                    <table className="min-w-full border-collapse text-left">
                      <thead>
                        <tr>
                          {["Date/time", "Risk score", "Status", "Trend"].map((label) => (
                            <th
                              key={label}
                              className="border-b border-[var(--dashboard-table-line)] bg-[color-mix(in_srgb,var(--dashboard-table-line)_30%,transparent)] px-4 py-3 text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted"
                            >
                              {label}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {detail.riskHistory.slice(0, 6).map((risk, index, history) => {
                          const historyTrend = getHistoryTrendIcon(index, history);

                          return (
                            <tr key={risk.id}>
                              <td className="border-b border-[var(--dashboard-table-line)] px-4 py-4 text-sm text-panel-copy last:border-b-0">
                                {formatOperationalTime(risk.generated_at)}
                              </td>
                              <td className="border-b border-[var(--dashboard-table-line)] px-4 py-4 text-sm font-semibold text-panel-strong last:border-b-0">
                                {Math.round(normalizeRiskScore(risk.score))}
                              </td>
                              <td className="border-b border-[var(--dashboard-table-line)] px-4 py-4 text-sm last:border-b-0">
                                <StatusBadge
                                  tone={getRiskBadgeTone(risk.risk_level)}
                                  className="rounded-full px-3 py-1 tracking-[0.14em]"
                                >
                                  {risk.risk_level}
                                </StatusBadge>
                              </td>
                              <td className="border-b border-[var(--dashboard-table-line)] px-4 py-4 text-sm last:border-b-0">
                                <span
                                  className={cn(
                                    "inline-flex size-8 items-center justify-center rounded-full",
                                    historyTrend === "up"
                                      ? "bg-[color-mix(in_srgb,var(--danger)_10%,white)] text-[color:var(--danger)]"
                                      : historyTrend === "down"
                                        ? "bg-[color-mix(in_srgb,var(--success)_10%,white)] text-[color:var(--success)]"
                                        : "bg-[color-mix(in_srgb,var(--dashboard-table-line)_40%,transparent)] text-panel-copy",
                                  )}
                                >
                                  {historyTrend === "up" ? (
                                    <ArrowUpRight className="size-4" aria-hidden="true" />
                                  ) : historyTrend === "down" ? (
                                    <ArrowUpRight className="size-4 rotate-90" aria-hidden="true" />
                                  ) : (
                                    <Minus className="size-4" aria-hidden="true" />
                                  )}
                                </span>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              ) : (
                <div className="rounded-[1.5rem] border border-dashed border-[var(--dashboard-table-line)] bg-[color-mix(in_srgb,var(--dashboard-table-line)_16%,transparent)] px-4 py-4">
                  <p className="text-sm font-semibold text-panel-strong">No risk trend available yet</p>
                  <p className="mt-1 text-sm text-panel-muted">Risk history will appear after multiple model runs.</p>
                </div>
              )}
            </Card>
          ) : null}

          <section className="grid gap-6 lg:grid-cols-2">
            <Card className="space-y-5 p-6">
              <div className="flex items-start gap-3">
                <span className="inline-flex size-11 shrink-0 items-center justify-center rounded-2xl bg-[color-mix(in_srgb,var(--dashboard-sidebar-title)_12%,white)] text-brand dark:bg-[color-mix(in_srgb,var(--dashboard-sidebar-title)_20%,transparent)]">
                  <MapPinned className="size-5" aria-hidden="true" />
                </span>
                <div className="space-y-1">
                  <h3 className="pt-1 text-xl font-semibold tracking-[-0.03em] text-panel-strong">Ward context</h3>
                  <p className="text-sm text-panel-muted">Operational context for this ward record.</p>
                </div>
              </div>

              {isLoading ? (
                <LoadingBlocks count={3} className="h-4 rounded-full bg-[color-mix(in_srgb,var(--dashboard-table-line)_55%,transparent)]" />
              ) : detail ? (
                <dl className="grid gap-4">
                  {[
                    ["Sub-county", detail.subCounty || "Not recorded"],
                    ["Ward code", detail.wardCode ?? "Not recorded"],
                    ["Trigger state", formatTriggerState(detail.triggerState)],
                    ["Latest record", formatOperationalTime(detail.updatedAt)],
                    ["Model status", detail.modelRunStatus ?? "Not available from current records"],
                    ["Predicted cases", String(detail.predictedCases)],
                  ].map(([label, value]) => (
                    <div
                      key={label}
                      className="grid gap-1 border-b border-[var(--dashboard-table-line)] pb-3 last:border-b-0 last:pb-0"
                    >
                      <dt className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted">{label}</dt>
                      <dd className="text-sm font-medium text-panel-strong">{value}</dd>
                    </div>
                  ))}
                </dl>
              ) : (
                <p className="text-sm text-panel-muted">No ward detail is available for this route.</p>
              )}
            </Card>

            <Card className="space-y-4 p-5">
              <div className="flex items-start gap-3">
                <span className="inline-flex size-11 shrink-0 items-center justify-center rounded-2xl bg-[color-mix(in_srgb,var(--dashboard-sidebar-title)_12%,white)] text-brand dark:bg-[color-mix(in_srgb,var(--dashboard-sidebar-title)_20%,transparent)]">
                  <MapPinned className="size-5" aria-hidden="true" />
                </span>
                <div className="space-y-1">
                  <h3 className="pt-1 text-xl font-semibold tracking-[-0.03em] text-panel-strong">Ward geography</h3>
                  <p className="text-sm text-panel-muted">Boundary preview only.</p>
                </div>
              </div>

              <p className="text-sm leading-6 text-panel-muted">
                This panel uses the shared Migori ward map contract. Neighboring ward analysis is not available yet.
              </p>

              <div className="overflow-hidden rounded-[1.5rem] border border-panel-table-wrap bg-[radial-gradient(circle_at_top_left,color-mix(in_srgb,var(--brand)_10%,transparent),transparent_35%),radial-gradient(circle_at_bottom_right,color-mix(in_srgb,var(--warning)_10%,transparent),transparent_32%),linear-gradient(135deg,color-mix(in_srgb,var(--panel)_92%,white),var(--panel))] p-3">
                <div className="flex h-full min-h-[15rem] flex-col gap-3 rounded-[1.1rem] border border-panel-table-wrap bg-panel/80 p-3">
                  <div className="flex items-center justify-between text-xs uppercase tracking-[0.18em] text-panel-subtle">
                    <span>Map context</span>
                    <span>{detail?.wardMapFeature ? "Backend geometry" : "No ward geometry"}</span>
                  </div>
                  <div className="min-h-[13.75rem] rounded-[1rem] border border-panel-table-wrap bg-white/60 p-2 dark:bg-panel/70">
                    {wardMapFeatures.length ? (
                      <MigoriWardMap
                        features={wardMapFeatures}
                        selectedWardCode={detail?.wardMapFeature?.properties.ward_code ?? null}
                        onSelectWard={() => undefined}
                      />
                    ) : (
                      <div className="flex h-full items-center justify-center text-center text-sm text-panel-muted">
                        Neighboring ward analysis not available yet.
                      </div>
                    )}
                  </div>
                  {detail?.wardMapFeature ? (
                    <div className="inline-flex w-max items-center gap-2 rounded-full bg-[color-mix(in_srgb,var(--brand)_10%,white)] px-3 py-1.5 text-xs font-semibold text-panel-strong dark:bg-[color-mix(in_srgb,var(--brand)_18%,transparent)]">
                      <span className="size-2 rounded-full bg-brand" />
                      {detail.wardName} boundary
                    </div>
                  ) : null}
                </div>
              </div>
            </Card>
          </section>
        </div>

        <aside className="space-y-6">
          <Card className="space-y-5 p-6">
            <div className="flex items-center gap-3">
              <span className="inline-flex size-11 items-center justify-center rounded-2xl bg-[color-mix(in_srgb,var(--dashboard-sidebar-title)_12%,white)] text-brand dark:bg-[color-mix(in_srgb,var(--dashboard-sidebar-title)_20%,transparent)]">
                <Zap className="size-5" aria-hidden="true" />
              </span>
              <div className="space-y-1">
                <h3 className="text-xl font-semibold tracking-[-0.03em] text-panel-strong">Recommended action</h3>
                <p className="text-sm text-panel-muted">The next truthful operator step for this ward.</p>
              </div>
            </div>

            {isLoading ? (
              <LoadingBlocks count={3} />
            ) : detail ? (
              <div className="space-y-4">
                <div className="rounded-[1.5rem] border border-[var(--dashboard-table-line)] bg-[color-mix(in_srgb,var(--dashboard-table-line)_20%,transparent)] px-4 py-4">
                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted">Primary action</p>
                  <p className="mt-2 text-base font-semibold text-panel-strong">
                    {recommendedActionState?.primaryAction}
                  </p>
                </div>

                <div className="rounded-[1.5rem] border border-[var(--dashboard-table-line)] bg-[color-mix(in_srgb,var(--dashboard-table-line)_16%,transparent)] px-4 py-4">
                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted">Why</p>
                  <p className="mt-2 text-sm leading-6 text-panel-copy">{recommendedActionState?.why}</p>
                </div>

                <div className="rounded-[1.5rem] border border-[var(--dashboard-table-line)] bg-[color-mix(in_srgb,var(--dashboard-table-line)_16%,transparent)] px-4 py-4">
                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted">Next steps</p>
                  <div className="mt-3 space-y-3">
                    {recommendedActionState?.nextSteps.map((step, index) => (
                      <div key={step} className="flex items-start gap-3">
                        <span className="inline-flex size-7 shrink-0 items-center justify-center rounded-full bg-[color-mix(in_srgb,var(--brand)_10%,white)] text-xs font-semibold text-brand">
                          {index + 1}
                        </span>
                        <p className="pt-1 text-sm font-medium text-panel-strong">{step}</p>
                      </div>
                    ))}
                  </div>
                </div>

                {detail.workflow?.expected_operational_effect ? (
                  <div className="rounded-[1.5rem] border border-[color-mix(in_srgb,var(--success)_18%,var(--dashboard-table-line))] bg-[color-mix(in_srgb,var(--success)_8%,var(--panel))] px-4 py-4">
                    <p className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted">Expected effect</p>
                    <p className="mt-2 text-sm leading-6 text-panel-copy">{detail.workflow.expected_operational_effect}</p>
                  </div>
                ) : null}

                {recommendations.length > 0 ? (
                  <div className="space-y-3">
                    <p className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted">Supporting checks</p>
                    {recommendations.map((recommendation) => (
                      <div
                        key={recommendation.text}
                        className="flex items-start gap-3 rounded-[1.25rem] border border-[var(--dashboard-table-line)] px-4 py-3"
                      >
                        <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-brand" aria-hidden="true" />
                        <p className="text-sm text-panel-copy">{recommendation.text}</p>
                      </div>
                    ))}
                  </div>
                ) : null}
              </div>
            ) : (
              <p className="text-sm text-panel-muted">No decision summary is available for this ward.</p>
            )}
          </Card>

          <Card className="space-y-5 p-6">
            <div className="flex items-center gap-3">
              <span className="inline-flex size-11 items-center justify-center rounded-2xl bg-[color-mix(in_srgb,var(--dashboard-sidebar-title)_12%,white)] text-brand dark:bg-[color-mix(in_srgb,var(--dashboard-sidebar-title)_20%,transparent)]">
                <Bell className="size-5" aria-hidden="true" />
              </span>
              <div className="space-y-1">
                <h3 className="text-xl font-semibold tracking-[-0.03em] text-panel-strong">Recent alerts</h3>
                <p className="text-sm text-panel-muted">Recent ward-linked alert activity with interpretation context.</p>
              </div>
            </div>

            {isLoading ? (
              <LoadingBlocks count={3} />
            ) : detail && detail.relatedAlerts.length > 0 ? (
              <>
                <div className="space-y-3">
                {detail.relatedAlerts.slice(0, 4).map((alert) => (
                  <article
                    key={alert.id}
                    className="rounded-[1.35rem] border border-[var(--dashboard-table-line)] bg-[color-mix(in_srgb,var(--dashboard-table-line)_28%,transparent)] px-4 py-4"
                  >
                    <div className="space-y-2">
                      <div className="flex flex-wrap items-center gap-2">
                        <strong className="text-sm font-semibold text-panel-strong">
                          {`${detail.riskLevel === "UNKNOWN" ? "Ward-linked" : formatRiskLevel(detail.riskLevel)} alert`} · {formatRelativeMinutes(alert.created_at)}
                        </strong>
                        <StatusBadge tone={getAlertTone(alert)} className="rounded-full px-3 py-1 tracking-[0.14em]">
                          {alert.status}
                        </StatusBadge>
                      </div>
                      <p className="text-sm text-panel-copy">Delivered ({toTitleCase(alert.channel)})</p>
                      <p className="text-sm text-panel-copy">
                        Predicted: {typeof detail.predictedCases === "number" ? detail.predictedCases : "Unavailable"} cases
                      </p>
                      <details className="text-sm text-panel-muted">
                        <summary className="cursor-pointer list-none font-medium text-panel-copy">View alert details</summary>
                        <div className="mt-2 space-y-1">
                          <p>
                            Risk score: {typeof alert.risk_score === "number" ? `${Math.round(normalizeRiskScore(alert.risk_score))}/100` : "Unavailable"}
                          </p>
                          <p>Alert message: {getAlertHeadline(alert)}</p>
                        </div>
                      </details>
                    </div>
                  </article>
                ))}
                </div>
                <Link
                  href="/alerts"
                  className="inline-flex items-center gap-2 text-sm font-semibold text-brand transition hover:text-[var(--login-link-hover)]"
                >
                  View full alert history
                  <ChevronRight className="size-4" aria-hidden="true" />
                </Link>
              </>
            ) : (
              <div className="rounded-[1.5rem] border border-dashed border-[var(--dashboard-table-line)] bg-[color-mix(in_srgb,var(--dashboard-table-line)_16%,transparent)] px-4 py-4">
                <p className="text-sm font-semibold text-panel-strong">No recent alerts for this ward</p>
                <p className="mt-1 text-sm text-panel-muted">
                  {detail?.primaryCtaKind === "OPEN_TRIGGER_FLOW" || detail?.primaryCtaKind === "REVIEW_TRIGGER"
                    ? canTriggerAlerts(currentUser.role)
                      ? detail.primaryCtaKind === "REVIEW_TRIGGER"
                        ? "Review trigger if guided follow-up is still needed."
                        : "Open trigger flow if a guided response is still needed."
                      : "Review alert history or coordinate with an authorized operator if a guided response is still needed."
                    : "Review full alert history if you need older ward-linked alert activity."}
                </p>
              </div>
            )}
          </Card>

          <Card className={cn("space-y-5 p-6", hasLowSignalState && "xl:sticky xl:top-24")}>
            <div className="flex items-center gap-3">
              <span className="inline-flex size-11 items-center justify-center rounded-2xl bg-[color-mix(in_srgb,var(--dashboard-sidebar-title)_12%,white)] text-brand dark:bg-[color-mix(in_srgb,var(--dashboard-sidebar-title)_20%,transparent)]">
                <Clock3 className="size-5" aria-hidden="true" />
              </span>
              <div className="space-y-1">
                <h3 className="text-xl font-semibold tracking-[-0.03em] text-panel-strong">Data status</h3>
                <p className="text-sm text-panel-muted">Compact freshness status with optional detail.</p>
              </div>
            </div>

            {isLoading ? (
              <LoadingBlocks count={3} className="h-4 rounded-full bg-[color-mix(in_srgb,var(--dashboard-table-line)_55%,transparent)]" />
            ) : detail ? (
              <details className="group rounded-[1.5rem] border border-[var(--dashboard-table-line)] bg-[color-mix(in_srgb,var(--dashboard-table-line)_16%,transparent)] px-4 py-4">
                <summary className="flex cursor-pointer list-none items-start justify-between gap-4">
                  <div className="space-y-1">
                    <p className="text-sm font-semibold text-panel-strong">
                      Data status: {detail.freshness.is_stale ? "Stale" : "In range"} ({formatRelativeMinutes(detail.updatedAt)})
                    </p>
                    <p className="text-sm text-panel-muted">
                      {detail.freshness.is_stale
                        ? "Review with caution until a fresher ward update lands."
                        : "Current ward data is inside the freshness window."}
                    </p>
                  </div>
                  <span className="pt-0.5 text-xs font-semibold uppercase tracking-[0.16em] text-brand transition group-open:text-panel-strong">
                    View details
                  </span>
                </summary>
                <div className="mt-4 space-y-4 border-t border-[var(--dashboard-table-line)] pt-4">
                  <dl className="grid gap-4">
                    {[
                      ["Freshness", detail.freshness.is_stale ? "Stale" : "In range"],
                      ["Recent runs", `${detail.freshness.history_count} recent runs`],
                      ["Alert linkage", `${detail.freshness.alert_count} recent alerts`],
                      ["Freshness window", `${detail.freshness.stale_threshold_minutes} minutes`],
                    ].map(([label, value]) => (
                      <div
                        key={label}
                        className="grid gap-1 border-b border-[var(--dashboard-table-line)] pb-3 last:border-b-0 last:pb-0"
                      >
                        <dt className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted">{label}</dt>
                        <dd className="text-sm font-medium text-panel-strong">{value}</dd>
                      </div>
                    ))}
                  </dl>

                  <p className="text-sm leading-6 text-panel-muted">
                    {detail.freshness.is_stale
                      ? `This ward summary is older than the ${detail.freshness.stale_threshold_minutes}-minute freshness window. Review with caution until the next update lands.`
                      : "Current ward data is inside the freshness window and can be used as the current operating view."}
                  </p>
                </div>
              </details>
            ) : (
              <p className="text-sm text-panel-muted">No freshness diagnostics are available for this ward.</p>
            )}
          </Card>
        </aside>
      </section>
    </div>
  );
}
