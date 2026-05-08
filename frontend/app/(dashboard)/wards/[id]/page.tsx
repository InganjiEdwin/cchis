"use client";

import {
  Activity,
  AlertTriangle,
  ArrowLeft,
  ArrowUpRight,
  BarChart3,
  Bell,
  CheckCircle2,
  ChevronRight,
  ClipboardCheck,
  Clock3,
  Droplets,
  Eye,
  History,
  MapPinned,
  Minus,
  Radio,
  ShieldAlert,
  UsersRound,
  Waves,
  Zap,
} from "lucide-react";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { useId, useMemo, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { DashboardTopbar } from "@/components/dashboard-topbar";
import { MigoriWardMap } from "@/components/migori-ward-map";
import { TriggerAlertPanel } from "@/components/trigger-alert-panel";
import { Card } from "@/components/ui/card";
import { StatusBadge } from "@/components/ui/status-badge";
import { cn } from "@/lib/cn";
import type { AlertRecord, ClimateEvidence, PreparednessActionRecord, RiskScoreRecord, WardIntelligenceDriverItem, WardOperationalEvidenceTone, WardPredictionOutcomeClassification, WardSpatialEvidence } from "@/lib/dashboard";
import { canTriggerAlerts } from "@/lib/roles";
import { type WardDetailState, useWardDetailQuery } from "@/queries/use-ward-detail-query";

import {
  LoadingBlocks,
  WardActionRail,
  WardCockpitHeader,
  WardDetailDisclosure,
  WardDetailTabs,
  WardMetricStrip,
  type WardDetailTabId,
} from "./ward-detail-sections";

const WARD_DETAIL_TABS: Array<{ id: WardDetailTabId; label: string }> = [
  { id: "situation", label: "Situation" },
  { id: "response", label: "Response" },
  { id: "evidence", label: "Evidence" },
  { id: "history", label: "History" },
];

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

function formatRiskBadgeLabel(riskLevel: WardDetailState["riskLevel"], isStale: boolean) {
  const label = formatRiskLevel(riskLevel);
  if (!isStale || riskLevel === "UNKNOWN") return label;
  return `Last known ${label.toLowerCase()}`;
}

function getRiskBadgeTooltip(detail: WardDetailState | null | undefined) {
  if (!detail) return "This will show the ward's risk level once the ward record finishes loading.";

  const riskLabel = formatRiskLevel(detail.riskLevel).toLowerCase();
  const stalePrefix = detail.freshness.is_stale ? "The last saved ward record showed" : "The latest ward record shows";

  if (detail.riskLevel === "HIGH") {
    return `${stalePrefix} ${riskLabel}. This means the ward needs close attention and the response history should be checked before taking the next step.`;
  }
  if (detail.riskLevel === "MEDIUM") {
    return `${stalePrefix} ${riskLabel}. This means the ward should stay on watch, especially if new alerts or field reports arrive.`;
  }
  if (detail.riskLevel === "LOW") {
    return `${stalePrefix} ${riskLabel}. This means routine monitoring is enough unless new risk signals appear.`;
  }
  return "The ward risk level is not clear from the available record, so use the evidence sections before making a decision.";
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
  if (driver.source_field?.startsWith("climate.")) {
    return <Droplets className="size-4" aria-hidden="true" />;
  }
  if (driver.source_field?.startsWith("spatial.")) {
    return <MapPinned className="size-4" aria-hidden="true" />;
  }

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

function getEvidenceTone(tone: WardOperationalEvidenceTone | undefined) {
  if (tone === "danger") return "danger" as const;
  if (tone === "warning") return "warning" as const;
  if (tone === "success") return "success" as const;
  return "default" as const;
}

function formatOutcomeClassification(classification: WardPredictionOutcomeClassification) {
  switch (classification) {
    case "hit":
      return "Hit";
    case "false_alert":
      return "False alert";
    case "missed_outbreak":
      return "Missed outbreak";
    case "correct_quiet":
      return "Correct quiet";
    case "pending_label":
    default:
      return "Pending label";
  }
}

function getOutcomeTone(classification: WardPredictionOutcomeClassification) {
  if (classification === "hit" || classification === "correct_quiet") return "success" as const;
  if (classification === "false_alert" || classification === "missed_outbreak") return "warning" as const;
  return "default" as const;
}

function formatShortDateRange(start: string | null, end: string | null) {
  const startDate = start ? new Date(start) : null;
  const endDate = end ? new Date(end) : null;
  if (!startDate || !endDate || Number.isNaN(startDate.getTime()) || Number.isNaN(endDate.getTime())) {
    return "Window unavailable";
  }
  return `${startDate.toLocaleDateString([], { month: "short", day: "numeric" })} - ${endDate.toLocaleDateString([], { month: "short", day: "numeric" })}`;
}

function formatDateOnly(value: string | null | undefined) {
  if (!value) return "Unavailable";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Invalid date";
  return date.toLocaleDateString([], { month: "short", day: "numeric", year: "numeric" });
}

function formatClimateValidRange(climate: ClimateEvidence | null) {
  if (!climate?.valid_date) return "Unavailable";
  const endDate = new Date(climate.valid_date);
  if (Number.isNaN(endDate.getTime())) return "Invalid date";
  const leadDay = climate.lead_day ?? climate.forecast_horizon_days;
  if (typeof leadDay === "number" && leadDay > 1) {
    const startDate = new Date(endDate);
    startDate.setDate(endDate.getDate() - leadDay + 1);
    return `${startDate.toLocaleDateString([], { month: "short", day: "numeric" })} - ${endDate.toLocaleDateString([], { month: "short", day: "numeric", year: "numeric" })}`;
  }
  return formatDateOnly(climate.valid_date);
}

function formatLeadDays(days: number[] | undefined) {
  if (!days?.length) return "None";
  if (days.length <= 8) return days.join(", ");
  return `${days.slice(0, 8).join(", ")} +${days.length - 8} more`;
}

function getClimateCoverageTone(climate: ClimateEvidence | null | undefined, missingLeadDays: number[] = []) {
  if (!climate) return "default" as const;
  if (climate.fallback_static_rainfall_used || missingLeadDays.length > 0) return "warning" as const;
  return climate.claimed_lead_time_climate_coverage_sufficient ? ("success" as const) : ("warning" as const);
}

function getClimateHorizonBadgeLabel(climate: ClimateEvidence | null | undefined, fallbackDays = 14) {
  const claimedDays = climate?.claimed_forecast_horizon_days ?? fallbackDays;
  if (!climate) return `${claimedDays}-day climate horizon unavailable`;
  if (climate.fallback_static_rainfall_used) return "Fallback climate source";
  if (climate.claimed_lead_time_climate_coverage_sufficient) return `${claimedDays}-day climate horizon covered`;
  return `${claimedDays}-day climate horizon caveated`;
}

function formatReviewState(value: string | undefined) {
  if (!value) return "Unavailable";
  return toTitleCase(value);
}

function formatFeedbackState(value: string | undefined) {
  if (!value) return "Unavailable";
  return toTitleCase(value);
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

function formatTriggerBadgeLabel(triggerState: WardDetailState["triggerState"], isStale: boolean) {
  if (triggerState === "RESOLVED") return isStale ? "Last response resolved" : "Response resolved";
  if (triggerState === "NONE") return isStale ? "Last known no active trigger" : "No active trigger";
  const label = formatTriggerState(triggerState);
  return isStale ? `Last known ${label.toLowerCase()}` : label;
}

function getTriggerBadgeTooltip(detail: WardDetailState | null | undefined) {
  if (!detail) return "This will show whether there is active response work for this ward once the record finishes loading.";

  const stalePrefix = detail.freshness.is_stale ? "In the last saved ward record," : "Right now,";

  if (detail.triggerState === "RESOLVED") {
    return `${stalePrefix} the response workflow is closed. Keep routine monitoring in place and reopen action only if conditions change.`;
  }
  if (detail.triggerState === "NONE") {
    return `${stalePrefix} there is no active trigger for this ward. Continue monitoring unless new risk signals appear.`;
  }
  if (detail.triggerState === "REVIEW_PENDING") {
    return `${stalePrefix} the ward needs someone to review the alert or trigger state before deciding the next action.`;
  }
  if (detail.triggerState === "ACTION_IN_PROGRESS") {
    return `${stalePrefix} response work is already underway. Check the Response tab for follow-through and open tasks.`;
  }
  if (detail.triggerState === "TRIGGER_ACTIVE") {
    return `${stalePrefix} an active trigger is open. Review the alert history and response actions before changing course.`;
  }
  return `${stalePrefix} the ward response state is ${formatTriggerState(detail.triggerState).toLowerCase()}. Check the Response tab for what has already happened.`;
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

type StatusTone = "danger" | "warning" | "success" | "default";

type CockpitBadge = {
  id: string;
  label: string;
  tone: StatusTone;
  tooltip: string;
};

function isWarningTone(tone: StatusTone) {
  return tone === "danger" || tone === "warning";
}

function getStatusTonePriority(tone: StatusTone) {
  if (tone === "danger") return 3;
  if (tone === "warning") return 2;
  if (tone === "success") return 1;
  return 0;
}

function getFreshnessBadgeTooltip(isStale: boolean) {
  return isStale
    ? "This ward has not been refreshed within the expected update window. Treat the page as useful background until a newer update is available."
    : "This ward was refreshed within the expected update window, so the page can be treated as the current operating view.";
}

function getClimateBadgeTooltip({
  fallbackUsed,
  isCovered,
  label,
  missingLeadDays,
}: {
  fallbackUsed?: boolean;
  isCovered?: boolean;
  label: string;
  missingLeadDays: number[];
}) {
  if (fallbackUsed) {
    return "The weather signal is coming from a backup source. Use it as helpful context, but do not treat it as a complete forecast picture.";
  }
  if (missingLeadDays.length > 0 || !isCovered) {
    return "The weather signal does not fully cover the forecast period shown here. Use it as a caution flag and check the Evidence tab for detail.";
  }
  return `${label} means the weather signal covers the expected forecast period for this ward view.`;
}

function getTrustCaveatTooltip(id: string, label: string) {
  if (id === "model") {
    return `${label} describes how ready the model evidence is for this ward view. Check the Evidence tab before relying on it alone.`;
  }
  if (id === "source") {
    return `${label} flags a caution about one of the inputs behind this ward view. Check the Evidence tab for the source detail.`;
  }
  return `${label} is a data quality note for this ward view. Check the Evidence tab for more context.`;
}

function CockpitBadgeWithTooltip({ badge }: { badge: CockpitBadge }) {
  const tooltipId = useId();
  const [isHovering, setIsHovering] = useState(false);
  const [isFocused, setIsFocused] = useState(false);
  const [isPinned, setIsPinned] = useState(false);
  const isVisible = isHovering || isFocused || isPinned;

  return (
    <span className="relative inline-flex">
      <button
        type="button"
        aria-describedby={tooltipId}
        aria-expanded={isVisible}
        className="inline-flex cursor-help rounded-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--panel)]"
        onBlur={() => {
          setIsFocused(false);
          setIsPinned(false);
        }}
        onClick={() => {
          setIsPinned((current) => !current);
        }}
        onFocus={() => {
          setIsFocused(true);
        }}
        onKeyDown={(event) => {
          if (event.key === "Escape") {
            setIsPinned(false);
            setIsFocused(false);
            event.currentTarget.blur();
          }
        }}
        onMouseEnter={() => {
          setIsHovering(true);
        }}
        onMouseLeave={() => {
          setIsHovering(false);
        }}
      >
        <StatusBadge
          tone={badge.tone}
          className="max-w-full whitespace-normal rounded-full px-2.5 py-1.5 text-center text-[0.68rem] leading-3 tracking-[0.12em] sm:text-xs"
        >
          {badge.label}
        </StatusBadge>
      </button>
      <span
        id={tooltipId}
        role="tooltip"
        className={cn(
          "pointer-events-none absolute left-0 top-full z-40 mt-2 w-[min(18rem,calc(100vw-3rem))] rounded-lg border border-[var(--dashboard-table-line)] bg-panel px-3 py-2 text-left text-xs font-medium normal-case leading-5 tracking-normal text-panel-copy shadow-panel transition duration-150 sm:left-1/2 sm:-translate-x-1/2",
          isVisible ? "visible translate-y-0 opacity-100" : "invisible -translate-y-1 opacity-0",
        )}
      >
        {badge.tooltip}
      </span>
    </span>
  );
}

function getAlertTone(alert: AlertRecord) {
  if (alert.status === "DELIVERED") return "success" as const;
  if (alert.status === "FAILED") return "danger" as const;
  return "warning" as const;
}

const PREPAREDNESS_ACTIVE_STATUSES = new Set<PreparednessActionRecord["status"]>([
  "DRAFT",
  "QUEUED",
  "ASSIGNED",
  "ACKNOWLEDGED",
  "IN_PROGRESS",
  "BLOCKED",
  "ESCALATED",
]);

const PREPAREDNESS_ACTION_TYPE_LABELS: Record<PreparednessActionRecord["action_type"], string> = {
  chv_follow_up: "CHV follow-up",
  household_prevention_message: "Household prevention message",
  facility_ors_review: "Facility ORS review",
  facility_staffing_review: "Facility staffing review",
  county_escalation: "County escalation",
  water_treatment_distribution: "Water treatment distribution",
  surveillance_follow_up: "Surveillance follow-up",
  field_verification: "Field verification",
};

function getPreparednessActionTone(action: PreparednessActionRecord) {
  if (action.is_overdue || action.status === "BLOCKED" || action.status === "ESCALATED") return "danger" as const;
  if (action.status === "COMPLETED") return "success" as const;
  if (action.status === "ACKNOWLEDGED" || action.status === "IN_PROGRESS" || action.status === "ASSIGNED") return "warning" as const;
  return "default" as const;
}

function getPreparednessActionSummary(actions: PreparednessActionRecord[]) {
  return actions.reduce(
    (summary, action) => {
      if (PREPAREDNESS_ACTIVE_STATUSES.has(action.status)) summary.active += 1;
      if (action.is_overdue) summary.overdue += 1;
      if (action.status === "BLOCKED") summary.blocked += 1;
      if (action.status === "COMPLETED") summary.completed += 1;
      return summary;
    },
    { active: 0, overdue: 0, blocked: 0, completed: 0 },
  );
}

function getOutcomeActionTone(status: string) {
  if (status === "recorded") return "success" as const;
  if (status === "in_progress") return "warning" as const;
  if (status === "failed" || status === "missing") return "danger" as const;
  return "default" as const;
}

function formatHours(value: number | null | undefined) {
  if (typeof value !== "number" || !Number.isFinite(value)) return "Not measured";
  return `${value}h`;
}

function formatSpatialDistance(value: number | null | undefined, unit?: string | null) {
  if (typeof value !== "number" || !Number.isFinite(value)) return "Unavailable";
  const rounded = value >= 10 ? value.toFixed(1) : value.toFixed(2);
  return `${rounded} ${unit === "source_crs_degrees" || !unit ? "source units" : unit}`;
}

function formatSpatialPercent(value: number | null | undefined) {
  if (typeof value !== "number" || !Number.isFinite(value)) return "Unavailable";
  return `${Math.round(value * 100)}%`;
}

function getSpatialReadinessTone(score: number | null | undefined) {
  if (typeof score !== "number" || !Number.isFinite(score)) return "default" as const;
  if (score >= 80) return "danger" as const;
  if (score >= 60) return "warning" as const;
  return "success" as const;
}

function getSpatialEvidenceHeadline(spatial: WardSpatialEvidence | null) {
  if (!spatial) return "Spatial context unavailable";
  if (spatial.summary.high_risk_neighbor_count > 0) {
    return `${spatial.summary.high_risk_neighbor_count} high-risk neighbor${spatial.summary.high_risk_neighbor_count === 1 ? "" : "s"}`;
  }
  if (spatial.summary.active_outbreak_neighbor_count > 0) {
    return `${spatial.summary.active_outbreak_neighbor_count} neighboring outbreak signal${spatial.summary.active_outbreak_neighbor_count === 1 ? "" : "s"}`;
  }
  return `${spatial.summary.neighbor_count} mapped neighbor${spatial.summary.neighbor_count === 1 ? "" : "s"}`;
}

function formatAlertChannel(channel: string | null | undefined) {
  if (!channel) return "unknown channel";
  const normalized = channel.toUpperCase();
  if (normalized === "SMS" || normalized === "EMAIL") return normalized;
  return toTitleCase(channel);
}

function getAlertSummary(alert: AlertRecord) {
  const channel = formatAlertChannel(alert.channel);
  const status = alert.status.toUpperCase();
  const deliveryState =
    status === "DELIVERED"
      ? `Delivered via ${channel}`
      : status === "QUEUED"
        ? `Queued for ${channel}`
        : status === "FAILED"
          ? `Failed via ${channel}`
          : status === "RETRY_PENDING"
            ? `Retry pending via ${channel}`
            : `${toTitleCase(alert.status)} via ${channel}`;
  const parts = [
    deliveryState,
  ];

  if (typeof alert.risk_score === "number") {
    parts.push(`Risk ${Math.round(normalizeRiskScore(alert.risk_score))}/100`);
  }

  return parts.join(" • ");
}

export default function WardDetailPage() {
  const params = useParams<{ id: string }>();
  const searchParams = useSearchParams();
  const { currentUser } = useAuth();
  const [activeTab, setActiveTab] = useState<WardDetailTabId>("situation");
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
  const spatialEvidence = detail?.spatialEvidence ?? null;
  const spatialSummary = spatialEvidence?.summary ?? null;
  const spatialMapFeatures =
    detail?.spatialMapFeatures && detail.spatialMapFeatures.length > 0
      ? detail.spatialMapFeatures
      : wardMapFeatures;
  const highRiskSpatialNeighbors = spatialEvidence?.neighbors.filter((neighbor) => neighbor.risk_level === "HIGH") ?? [];
  const canTriggerFromPage = canTriggerAlerts(currentUser);
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
  const operationalEvidence = detail?.operationalEvidence ?? null;
  const forecastHorizon = operationalEvidence?.forecast_horizon ?? null;
  const climateSource = operationalEvidence?.climate_source ?? null;
  const climateMissingLeadDays = climateSource?.forecast_missing_lead_days ?? forecastHorizon?.forecast_missing_lead_days ?? [];
  const climateSourceLabel =
    climateSource?.observed_vs_forecast_source_label || forecastHorizon?.source_label || "Climate source unavailable";
  const modelReadiness = operationalEvidence?.model_readiness ?? null;
  const alertCandidateReview = operationalEvidence?.alert_candidate_review ?? null;
  const outcomeEvaluation = operationalEvidence?.outcome_evaluation ?? null;
  const predictionLabelHistory = operationalEvidence?.prediction_label_history ?? [];
  const falseMissedReview = operationalEvidence?.false_missed_review ?? null;
  const chvActionStatus = operationalEvidence?.chv_action_status ?? null;
  const outcomeFeedback = operationalEvidence?.outcome_feedback ?? null;
  const preparednessActions = detail?.preparednessActions ?? [];
  const preparednessActionSummary = useMemo(
    () => getPreparednessActionSummary(preparednessActions),
    [preparednessActions],
  );
  const climateCoverageTone = getClimateCoverageTone(climateSource, climateMissingLeadDays);
  const sourceTrustCaveatBadge = operationalEvidence?.source_badges.find((badge) =>
    isWarningTone(getEvidenceTone(badge.tone)),
  );
  const strongestTrustCaveat = [
    forecastHorizon && isWarningTone(climateCoverageTone)
      ? {
          id: "climate",
          label: getClimateHorizonBadgeLabel(climateSource, forecastHorizon.max_days),
          tone: climateCoverageTone,
          tooltip: getClimateBadgeTooltip({
            fallbackUsed: climateSource?.fallback_static_rainfall_used,
            isCovered: climateSource?.claimed_lead_time_climate_coverage_sufficient,
            label: getClimateHorizonBadgeLabel(climateSource, forecastHorizon.max_days),
            missingLeadDays: climateMissingLeadDays,
          }),
        }
      : null,
    modelReadiness && isWarningTone(getEvidenceTone(modelReadiness.tone))
      ? {
          id: "model",
          label: modelReadiness.label,
          tone: getEvidenceTone(modelReadiness.tone),
          tooltip: getTrustCaveatTooltip("model", modelReadiness.label),
        }
      : null,
    sourceTrustCaveatBadge
      ? {
          id: "source",
          label: sourceTrustCaveatBadge.value,
          tone: getEvidenceTone(sourceTrustCaveatBadge.tone),
          tooltip: getTrustCaveatTooltip("source", sourceTrustCaveatBadge.value),
        }
      : null,
  ]
    .filter((item): item is CockpitBadge => Boolean(item))
    .sort((left, right) => getStatusTonePriority(right.tone) - getStatusTonePriority(left.tone))[0] ?? null;
  const cockpitOperationalBadges = isLoading
    ? []
    : [
        {
          id: "risk",
          label: formatRiskBadgeLabel(detail?.riskLevel ?? "UNKNOWN", detail?.freshness.is_stale ?? true),
          tone: getRiskBadgeTone(detail?.riskLevel ?? "UNKNOWN"),
          tooltip: getRiskBadgeTooltip(detail),
        },
        {
          id: "trigger",
          label: formatTriggerBadgeLabel(detail?.triggerState ?? "NONE", detail?.freshness.is_stale ?? true),
          tone: getTriggerTone(detail?.triggerState ?? "NONE"),
          tooltip: getTriggerBadgeTooltip(detail),
        },
      ];
  const cockpitDataQualityBadges = isLoading
    ? []
    : [
        {
          id: "freshness",
          label: detail?.freshness.is_stale ? "Stale data" : "Fresh data",
          tone: getFreshnessTone(detail?.freshness.is_stale ?? true),
          tooltip: getFreshnessBadgeTooltip(detail?.freshness.is_stale ?? true),
        },
        ...(strongestTrustCaveat ? [strongestTrustCaveat] : []),
      ];
  const sourceConfidenceBadge =
    operationalEvidence?.source_badges.find((badge) => badge.id === "source_confidence") ??
    operationalEvidence?.source_badges[1] ??
    null;
  const cockpitTrustItems = [
    modelReadiness ? `Model: ${modelReadiness.label}` : null,
    forecastHorizon ? `Climate: ${getClimateHorizonBadgeLabel(climateSource, forecastHorizon.max_days)}` : null,
    sourceConfidenceBadge ? `${sourceConfidenceBadge.value} confidence` : null,
  ].filter((item): item is string => Boolean(item));
  const cockpitActionNudge = detail
    ? shouldShowTriggerPanelPrimary
      ? null
      : canTriggerFromPage
        ? "Review alert history first."
        : "Read-only trigger access."
    : null;
  const actionRailOperatingNote = detail
    ? shouldShowTriggerPanelPrimary
      ? "Trigger review and alert handling continue in dedicated workflows after this checkpoint."
      : canTriggerFromPage
        ? "Review alert history first. Open trigger flow only if conditions change."
        : "Recommendation is visible, but this role cannot start or review trigger work from this page."
    : null;

  if (!currentUser) {
    return null;
  }

  return (
    <div className="space-y-6">
      <DashboardTopbar
        title="Ward Decision"
        subtitle={detail ? `${detail.county} County ward operating view` : "Migori County ward operating view"}
        lastUpdatedLabel={topbarTimestampLabel}
        lastUpdatedTone={isStale ? "stale" : "default"}
        onRefresh={() => {
          void wardDetailQuery.refetch();
        }}
      />

      {error ? (
        <div className="rounded-lg border border-[color-mix(in_srgb,var(--danger)_20%,white)] bg-[color-mix(in_srgb,var(--danger)_10%,white)] p-4 text-sm font-medium text-[color:var(--danger)]">
          <AlertTriangle className="mr-2 inline-flex size-4" aria-hidden="true" />
          {error}
        </div>
      ) : null}

      <WardCockpitHeader>
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="space-y-4">
            <Link
              href={returnTo}
              className="inline-flex items-center gap-2 text-sm font-semibold text-brand transition hover:text-[var(--login-link-hover)]"
            >
              <ArrowLeft className="size-4" aria-hidden="true" />
              Back to wards
            </Link>

            <div className="space-y-4">
              <div className="space-y-3">
                <div className="flex flex-wrap items-center gap-3">
                  <h1 className="text-3xl font-semibold leading-tight text-panel-strong md:text-4xl">
                    {isLoading ? "Loading ward detail..." : detail?.wardName ?? "Ward detail"}
                  </h1>
                  {!isLoading
                    ? cockpitOperationalBadges.map((badge) => (
                        <CockpitBadgeWithTooltip key={badge.id} badge={badge} />
                      ))
                    : null}
                </div>

                {!isLoading && cockpitDataQualityBadges.length ? (
                  <div className="flex flex-wrap items-center gap-2.5" aria-label="Ward data quality">
                    <span className="text-[0.68rem] font-semibold uppercase tracking-[0.14em] text-panel-subtle sm:text-xs">Data quality</span>
                    {cockpitDataQualityBadges.map((badge) => (
                      <CockpitBadgeWithTooltip key={badge.id} badge={badge} />
                    ))}
                  </div>
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
                <p className="text-lg font-semibold text-panel-strong">
                  {isLoading ? "Loading decision summary..." : decisionCheckpointCopy.headline}
                </p>
                <p className="max-w-2xl text-sm leading-6 text-panel-muted max-[640px]:hidden">
                  {isLoading ? "Checking current trigger state, alert activity, and freshness." : decisionCheckpointCopy.why}
                </p>
                {!isLoading ? (
                  <p className="text-xs font-medium uppercase tracking-[0.16em] text-panel-subtle max-[640px]:hidden">
                    {decisionCheckpointCopy.context}
                  </p>
                ) : null}
              </div>
            </div>
          </div>

          <div className="w-full max-w-md space-y-4 lg:pl-6">
            {detail ? (
              shouldShowTriggerPanelPrimary ? (
                <TriggerAlertPanel
                  buttonLabel={primaryTriggerButtonLabel}
                  closeLabel={primaryTriggerCloseLabel}
                  buttonClassName="inline-flex min-h-12 w-full items-center justify-center gap-2 rounded-pill bg-[var(--login-submit-start)] px-6 py-3 text-center text-base font-semibold leading-5 text-white shadow-[var(--login-submit-shadow)] transition hover:bg-[var(--login-submit-end)] hover:shadow-[var(--login-submit-shadow-hover)]"
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
                <div className="flex items-start gap-2 rounded-lg border border-[color-mix(in_srgb,var(--warning)_18%,white)] bg-[color-mix(in_srgb,var(--warning)_8%,white)] p-4 text-sm font-medium text-[color:var(--warning)] dark:border-[color-mix(in_srgb,var(--warning)_24%,var(--panel-border))] dark:bg-[color-mix(in_srgb,var(--warning)_14%,var(--panel))] dark:text-[color-mix(in_srgb,var(--warning)_78%,white)]">
                  <AlertTriangle className="mt-0.5 inline-flex size-4 shrink-0" aria-hidden="true" />
                  <span>{cockpitActionNudge}</span>
                </div>
              )
            ) : null}

            <div className="grid gap-4 sm:grid-cols-2">
              <Link
                href="/alerts"
                className={cn(
                  "inline-flex min-h-12 w-full items-center justify-center gap-2 rounded-pill px-6 py-3 text-center text-sm font-semibold leading-5 transition sm:col-span-2",
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
                  buttonClassName="inline-flex min-h-12 w-full items-center justify-center gap-2 rounded-pill border border-[var(--dashboard-table-line)] bg-[color-mix(in_srgb,var(--dashboard-table-line)_18%,transparent)] px-6 py-3 text-center text-sm font-semibold leading-5 text-panel-strong transition hover:bg-[color-mix(in_srgb,var(--dashboard-table-line)_34%,transparent)]"
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

            {cockpitTrustItems.length > 0 ? (
              <div className="rounded-lg border border-[var(--dashboard-table-line)] bg-[color-mix(in_srgb,var(--dashboard-table-line)_14%,transparent)] p-4">
                <p className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted">Trust</p>
                <div className="mt-2 flex flex-wrap gap-2">
                  {cockpitTrustItems.map((item) => (
                    <span
                      key={item}
                      className="inline-flex max-w-full rounded-full bg-[color-mix(in_srgb,var(--dashboard-table-line)_28%,transparent)] px-3 py-2 text-xs font-semibold leading-4 text-panel-copy"
                    >
                      {item}
                    </span>
                  ))}
                </div>
              </div>
            ) : null}
          </div>
        </div>

        <WardMetricStrip
          metrics={[
            { label: "Risk score", value: isLoading ? "Loading..." : formatRiskScore(detail?.riskScore ?? null) },
            { label: "Expected cases", value: isLoading ? "Loading..." : detail ? String(detail.predictedCases) : "Unavailable" },
            { label: "Last alert", value: isLoading ? "Loading..." : detail?.lastAlertAt ? formatRelativeMinutes(detail.lastAlertAt) : "No recent alerts" },
            { label: "Latest record", value: isLoading ? "Loading..." : formatOperationalTime(detail?.updatedAt ?? null) },
          ]}
        />
      </WardCockpitHeader>

      <WardDetailTabs activeTab={activeTab} tabs={WARD_DETAIL_TABS} onSelectTab={setActiveTab} />

      {activeTab === "evidence" ? (
      <Card className="space-y-6 p-6">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="flex items-center gap-4">
            <span className="inline-flex size-11 items-center justify-center rounded-lg bg-[color-mix(in_srgb,var(--dashboard-sidebar-title)_12%,white)] text-brand dark:bg-[color-mix(in_srgb,var(--dashboard-sidebar-title)_20%,transparent)]">
              <Radio className="size-5" aria-hidden="true" />
            </span>
            <div className="space-y-1">
              <h3 className="text-xl font-semibold text-panel-strong">Forecast horizon and evidence</h3>
              <p className="text-sm text-panel-muted">Current lead-time window, source quality, and model readiness for this ward.</p>
            </div>
          </div>
          {modelReadiness ? (
            <StatusBadge tone={getEvidenceTone(modelReadiness.tone)} className="w-max rounded-full px-3 py-1 tracking-[0.14em]">
              {modelReadiness.label}
            </StatusBadge>
          ) : null}
        </div>

        {isLoading ? (
          <LoadingBlocks count={3} className="h-12 rounded-lg bg-[color-mix(in_srgb,var(--dashboard-table-line)_55%,transparent)]" />
        ) : operationalEvidence ? (
          <div className="grid gap-4 lg:grid-cols-[minmax(0,0.95fr)_minmax(0,1.35fr)]">
            <div className="rounded-lg border border-[var(--dashboard-table-line)] bg-[color-mix(in_srgb,var(--dashboard-table-line)_18%,transparent)] px-4 py-4">
              <div className="flex items-start gap-4">
                <span className="inline-flex size-10 shrink-0 items-center justify-center rounded-full bg-[color-mix(in_srgb,var(--brand)_10%,white)] text-brand">
                  <Activity className="size-4" aria-hidden="true" />
                </span>
                <div className="space-y-2">
                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted">Forecast horizon</p>
                  <p className="text-2xl font-semibold text-panel-strong">
                    {forecastHorizon?.display_value ?? "7 to 14 days"}
                  </p>
                  <p className="text-sm leading-6 text-panel-muted">
                    {forecastHorizon?.expected_cases_label ?? "Expected cases in the next 7 days"}:{" "}
                    <span className="font-semibold text-panel-strong">{detail?.predictedCases ?? "Unavailable"}</span>
                  </p>
                  <p className="text-sm leading-6 text-panel-muted">
                    Lead-time validation: {forecastHorizon?.validation_status ? toTitleCase(forecastHorizon.validation_status) : "Not yet linked"}
                  </p>
                </div>
              </div>
            </div>

            <div className="grid gap-4 md:grid-cols-3">
              {operationalEvidence.source_badges.map((badge) => (
                <div
                  key={badge.id}
                  className="rounded-lg border border-[var(--dashboard-table-line)] bg-[color-mix(in_srgb,var(--dashboard-table-line)_16%,transparent)] px-4 py-4"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted">{badge.label}</p>
                    <StatusBadge
                      tone={getEvidenceTone(badge.tone)}
                      className="max-w-full whitespace-normal rounded-full px-2 py-0.5 text-center leading-4 tracking-[0.12em]"
                    >
                      {badge.value}
                    </StatusBadge>
                  </div>
                  <p className="mt-4 text-sm leading-6 text-panel-copy">{badge.detail}</p>
                </div>
              ))}
            </div>

            <WardDetailDisclosure
              title="Climate source truth"
              summary={
                climateMissingLeadDays.length > 0
                  ? `${climateSourceLabel}; missing lead days: ${formatLeadDays(climateMissingLeadDays)}.`
                  : `${climateSourceLabel}; ${climateSource?.source_provider || "source provider unavailable"}.`
              }
              badge={climateSource?.climate_coverage_status ? toTitleCase(climateSource.climate_coverage_status) : "Coverage unavailable"}
              badgeTone={getClimateCoverageTone(climateSource, climateMissingLeadDays)}
              className="lg:col-span-2"
            >
              <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
                {[
                  ["Provider", climateSource?.source_provider || "Source provider unavailable"],
                  ["Issue time", formatOperationalTime(climateSource?.issue_time ?? null)],
                  ["Valid dates", formatClimateValidRange(climateSource)],
                  ["Coverage", `${climateSource?.forecast_coverage_days ?? 0}/${climateSource?.claimed_forecast_horizon_days ?? forecastHorizon?.max_days ?? 14} days`],
                  ["Missing lead days", formatLeadDays(climateMissingLeadDays)],
                ].map(([label, value]) => (
                  <div key={label} className="rounded-lg border border-[var(--dashboard-table-line)] p-4">
                    <p className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted">{label}</p>
                    <p className="mt-2 text-sm font-semibold text-panel-strong">{value}</p>
                  </div>
                ))}
              </div>

              {climateSource?.fallback_static_rainfall_used ? (
                <div className="mt-4 flex items-start gap-2 rounded-lg border border-[color-mix(in_srgb,var(--warning)_20%,var(--dashboard-table-line))] bg-[color-mix(in_srgb,var(--warning)_8%,var(--panel))] p-4">
                  <AlertTriangle className="mt-0.5 size-4 shrink-0 text-[color:var(--warning)]" aria-hidden="true" />
                  <p className="text-sm leading-6 text-panel-copy">
                    Fallback static rainfall is present and must not be treated as live forecast evidence.
                  </p>
                </div>
              ) : null}

              {climateMissingLeadDays.length > 0 ? (
                <div className="mt-4 flex items-start gap-2 rounded-lg border border-[color-mix(in_srgb,var(--warning)_20%,var(--dashboard-table-line))] bg-[color-mix(in_srgb,var(--warning)_8%,var(--panel))] p-4">
                  <AlertTriangle className="mt-0.5 size-4 shrink-0 text-[color:var(--warning)]" aria-hidden="true" />
                  <p className="text-sm leading-6 text-panel-copy">
                    Missing forecast lead days: {formatLeadDays(climateMissingLeadDays)}.
                  </p>
                </div>
              ) : null}
            </WardDetailDisclosure>

            <WardDetailDisclosure
              title="Model readiness evidence"
              summary={modelReadiness?.detail ?? "No model-readiness evidence is available."}
              badge={modelReadiness?.label ?? "No evidence"}
              badgeTone={modelReadiness ? getEvidenceTone(modelReadiness.tone) : "default"}
              className="lg:col-span-2"
            >
              {modelReadiness?.evidence.length ? (
                <div className="flex flex-wrap gap-2">
                  {modelReadiness.evidence.slice(0, 5).map((item) => (
                    <span
                      key={item}
                      className="inline-flex rounded-full bg-[color-mix(in_srgb,var(--dashboard-table-line)_34%,transparent)] px-3 py-1 text-xs font-semibold text-panel-copy"
                    >
                      {item}
                    </span>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-panel-muted">No model-readiness evidence is available.</p>
              )}
            </WardDetailDisclosure>
          </div>
        ) : (
          <div className="rounded-lg border border-dashed border-[var(--dashboard-table-line)] bg-[color-mix(in_srgb,var(--dashboard-table-line)_16%,transparent)] px-4 py-4">
            <p className="text-sm font-semibold text-panel-strong">Operational evidence is not available yet.</p>
            <p className="mt-1 text-sm text-panel-muted">Ward risk state is visible, but source confidence and outcome evidence are not linked for this record.</p>
          </div>
        )}
      </Card>
      ) : null}

      <section className="grid items-start gap-6 xl:grid-cols-[minmax(0,1.5fr)_minmax(320px,0.9fr)]">
        <div className="space-y-6">
          {activeTab === "situation" ? (
          <Card className="space-y-6 p-6">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
              <div className="flex items-center gap-4">
                <span className="inline-flex size-11 items-center justify-center rounded-lg bg-[color-mix(in_srgb,var(--warning)_12%,white)] text-[color:var(--warning)] dark:bg-[color-mix(in_srgb,var(--warning)_20%,transparent)]">
                  <ShieldAlert className="size-5" aria-hidden="true" />
                </span>
                <div className="space-y-1">
                  <h3 className="text-xl font-semibold text-panel-strong">
                    {hasLowSignalState ? "Risk signals & trend" : "Risk explanation"}
                  </h3>
                  <p className="text-sm text-panel-muted">
                    {hasLowSignalState ? "Single low-signal checkpoint for this ward." : "Top drivers and source context from the latest ward records."}
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
              <div className="rounded-lg border border-dashed border-[var(--dashboard-table-line)] bg-[color-mix(in_srgb,var(--dashboard-table-line)_16%,transparent)] px-4 py-4">
                <p className="text-sm font-semibold text-panel-strong">No active signals or trends detected.</p>
                <p className="mt-1 text-sm text-panel-muted">This ward is currently under routine monitoring.</p>
                <p className="mt-1 text-sm text-panel-muted">
                  Latest record: {detail?.updatedAt ? formatOperationalTime(detail.updatedAt) : "Unavailable"}
                </p>
              </div>
            ) : drivers.length > 0 ? (
              <div className="space-y-4">
                {drivers.map((driver) => (
                  <article
                    key={driver.text}
                    className="flex items-center gap-4 rounded-lg border border-[var(--dashboard-table-line)] bg-[color-mix(in_srgb,var(--dashboard-table-line)_28%,transparent)] px-4 py-4"
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
              <div className="rounded-lg border border-dashed border-[var(--dashboard-table-line)] bg-[color-mix(in_srgb,var(--dashboard-table-line)_16%,transparent)] px-4 py-4">
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
          ) : null}

          {activeTab === "history" && !hasLowSignalState ? (
            <Card className="space-y-6 p-6">
              <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                <div className="flex items-center gap-4">
                  <span className="inline-flex size-11 items-center justify-center rounded-lg bg-[color-mix(in_srgb,var(--dashboard-sidebar-title)_12%,white)] text-brand dark:bg-[color-mix(in_srgb,var(--dashboard-sidebar-title)_20%,transparent)]">
                    <Waves className="size-5" aria-hidden="true" />
                  </span>
                  <div className="space-y-1">
                    <h3 className="text-xl font-semibold text-panel-strong">Risk history</h3>
                    <p className="text-sm text-panel-muted">Compact record of recent ward runs.</p>
                  </div>
                </div>
              </div>

              {isLoading ? (
                <LoadingBlocks count={4} className="h-14 rounded-lg bg-[color-mix(in_srgb,var(--dashboard-table-line)_55%,transparent)]" />
              ) : detail && detail.riskHistory.length > 0 ? (
                <div className="overflow-hidden rounded-lg border border-[var(--dashboard-table-line)]">
                  <div className="overflow-x-auto">
                    <table className="min-w-full border-collapse text-left">
                      <thead>
                        <tr>
                          {["Date/time", "Risk score", "Status", "Trend"].map((label) => (
                            <th
                              key={label}
                              className="border-b border-[var(--dashboard-table-line)] bg-[color-mix(in_srgb,var(--dashboard-table-line)_30%,transparent)] p-4 text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted"
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
                <div className="rounded-lg border border-dashed border-[var(--dashboard-table-line)] bg-[color-mix(in_srgb,var(--dashboard-table-line)_16%,transparent)] px-4 py-4">
                  <p className="text-sm font-semibold text-panel-strong">No risk trend available yet</p>
                  <p className="mt-1 text-sm text-panel-muted">Risk history will appear after multiple model runs.</p>
                </div>
              )}
            </Card>
          ) : null}

          {activeTab === "evidence" ? (
          <Card className="space-y-6 p-6">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
              <div className="flex items-center gap-4">
                <span className="inline-flex size-11 items-center justify-center rounded-lg bg-[color-mix(in_srgb,var(--dashboard-sidebar-title)_12%,white)] text-brand dark:bg-[color-mix(in_srgb,var(--dashboard-sidebar-title)_20%,transparent)]">
                  <BarChart3 className="size-5" aria-hidden="true" />
                </span>
                <div className="space-y-1">
                  <h3 className="text-xl font-semibold text-panel-strong">Prediction outcomes</h3>
                  <p className="text-sm text-panel-muted">Recent predictions compared with observed surveillance label windows.</p>
                </div>
              </div>
              {falseMissedReview ? (
                <StatusBadge
                  tone={falseMissedReview.open_review_count > 0 ? "warning" : "success"}
                  className="w-max rounded-full px-3 py-1 tracking-[0.14em]"
                >
                  {falseMissedReview.open_review_count} review item{falseMissedReview.open_review_count === 1 ? "" : "s"}
                </StatusBadge>
              ) : null}
            </div>

            {isLoading ? (
              <LoadingBlocks count={4} className="h-14 rounded-lg bg-[color-mix(in_srgb,var(--dashboard-table-line)_55%,transparent)]" />
            ) : outcomeEvaluation ? (
              <div className="space-y-4">
                <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
                  {[
                    ["Evaluated", outcomeEvaluation.evaluated_count],
                    ["Hits", outcomeEvaluation.hit_count],
                    ["False alerts", outcomeEvaluation.false_alert_count],
                    ["Missed outbreaks", outcomeEvaluation.missed_outbreak_count],
                    ["Pending labels", outcomeEvaluation.pending_label_count],
                  ].map(([label, value]) => (
                    <div
                      key={label}
                      className="rounded-lg border border-[var(--dashboard-table-line)] bg-[color-mix(in_srgb,var(--dashboard-table-line)_18%,transparent)] p-4"
                    >
                      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted">{label}</p>
                      <p className="mt-2 text-xl font-semibold text-panel-strong">{value}</p>
                    </div>
                  ))}
                </div>

                {predictionLabelHistory.length > 0 ? (
                  <div className="overflow-hidden rounded-lg border border-[var(--dashboard-table-line)]">
                    <div className="overflow-x-auto">
                      <table className="min-w-full table-fixed border-collapse text-left">
                        <thead>
                          <tr>
                            {["Prediction", "Forecast window", "Predicted", "Observed", "Outcome"].map((label) => (
                              <th
                                key={label}
                                className="border-b border-[var(--dashboard-table-line)] bg-[color-mix(in_srgb,var(--dashboard-table-line)_30%,transparent)] p-4 text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted"
                              >
                                {label}
                              </th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {predictionLabelHistory.slice(0, 5).map((row) => (
                            <tr key={row.risk_score_id}>
                              <td className="border-b border-[var(--dashboard-table-line)] px-4 py-4 text-sm text-panel-copy last:border-b-0">
                                {formatOperationalTime(row.prediction_generated_at)}
                              </td>
                              <td className="border-b border-[var(--dashboard-table-line)] px-4 py-4 text-sm text-panel-copy last:border-b-0">
                                {formatShortDateRange(row.forecast_window_start, row.forecast_window_end)}
                              </td>
                              <td className="border-b border-[var(--dashboard-table-line)] px-4 py-4 text-sm text-panel-copy last:border-b-0">
                                {row.risk_level} · {row.predicted_cases} cases
                              </td>
                              <td className="border-b border-[var(--dashboard-table-line)] px-4 py-4 text-sm text-panel-copy last:border-b-0">
                                {toTitleCase(row.observed_label)}
                              </td>
                              <td className="border-b border-[var(--dashboard-table-line)] px-4 py-4 text-sm last:border-b-0">
                                <StatusBadge
                                  tone={getOutcomeTone(row.classification)}
                                  className="max-w-full whitespace-normal rounded-full px-3 py-1 text-center leading-4 tracking-[0.14em]"
                                >
                                  {formatOutcomeClassification(row.classification)}
                                </StatusBadge>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                ) : (
                  <div className="rounded-lg border border-dashed border-[var(--dashboard-table-line)] bg-[color-mix(in_srgb,var(--dashboard-table-line)_16%,transparent)] px-4 py-4">
                    <p className="text-sm font-semibold text-panel-strong">No prediction outcome history yet</p>
                    <p className="mt-1 text-sm text-panel-muted">Outcome rows appear when predictions can be matched to future surveillance label windows.</p>
                  </div>
                )}

                {falseMissedReview?.items.length ? (
                  <div className="space-y-4">
                    <p className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted">False-alert and missed-outbreak review workflow</p>
                    {falseMissedReview.items.slice(0, 3).map((item) => (
                      <div
                        key={`${item.classification}-${item.risk_score_id}`}
                        className="rounded-lg border border-[color-mix(in_srgb,var(--warning)_20%,var(--dashboard-table-line))] bg-[color-mix(in_srgb,var(--warning)_8%,var(--panel))] p-4"
                      >
                        <div className="flex flex-wrap items-center gap-2">
                          <StatusBadge tone="warning" className="max-w-full whitespace-normal rounded-full px-3 py-1 text-center leading-4 tracking-[0.14em]">
                            {formatOutcomeClassification(item.classification)}
                          </StatusBadge>
                          <span className="text-sm font-semibold text-panel-strong">{item.label_window_ref || "No label ref"}</span>
                        </div>
                        <p className="mt-2 text-sm leading-6 text-panel-copy">{item.recommended_review_action}</p>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-sm text-panel-muted">{falseMissedReview?.workflow_label ?? "No outcome review workflow is available yet."}</p>
                )}
              </div>
            ) : (
              <div className="rounded-lg border border-dashed border-[var(--dashboard-table-line)] bg-[color-mix(in_srgb,var(--dashboard-table-line)_16%,transparent)] px-4 py-4">
                <p className="text-sm font-semibold text-panel-strong">Outcome evaluation is not available yet.</p>
                <p className="mt-1 text-sm text-panel-muted">Users can still review current risk and alert state while label-linked evaluation is pending.</p>
              </div>
            )}
          </Card>
          ) : null}

          {activeTab === "evidence" ? (
          <Card className="space-y-6 p-6">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
              <div className="flex items-center gap-4">
                <span className="inline-flex size-11 items-center justify-center rounded-lg bg-[color-mix(in_srgb,var(--dashboard-sidebar-title)_12%,white)] text-brand dark:bg-[color-mix(in_srgb,var(--dashboard-sidebar-title)_20%,transparent)]">
                  <Activity className="size-5" aria-hidden="true" />
                </span>
                <div className="space-y-1">
                  <h3 className="text-xl font-semibold text-panel-strong">Outcome feedback loop</h3>
                  <p className="text-sm text-panel-muted">Model outcome separated from downstream response execution.</p>
                </div>
              </div>
              {outcomeFeedback ? (
                <StatusBadge
                  tone={outcomeFeedback.summary.downstream_failure_count > 0 ? "danger" : outcomeFeedback.summary.review_item_count > 0 ? "warning" : "success"}
                  className="w-max rounded-full px-3 py-1 tracking-[0.14em]"
                >
                  {formatFeedbackState(outcomeFeedback.attribution)}
                </StatusBadge>
              ) : null}
            </div>

            {isLoading ? (
              <LoadingBlocks count={4} className="h-14 rounded-lg bg-[color-mix(in_srgb,var(--dashboard-table-line)_55%,transparent)]" />
            ) : outcomeFeedback ? (
              <div className="space-y-6">
                <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
                  {[
                    ["Model quality", formatFeedbackState(outcomeFeedback.model_quality_state)],
                    ["Response quality", formatFeedbackState(outcomeFeedback.response_quality_state)],
                    ["Observed outcome", outcomeFeedback.observed_outcome.label],
                    ["Review items", String(outcomeFeedback.summary.review_item_count)],
                  ].map(([label, value]) => (
                    <div
                      key={label}
                      className="rounded-lg border border-[var(--dashboard-table-line)] bg-[color-mix(in_srgb,var(--dashboard-table-line)_18%,transparent)] p-4"
                    >
                      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted">{label}</p>
                      <p className="mt-2 text-sm font-semibold text-panel-strong">{value}</p>
                    </div>
                  ))}
                </div>

                <div className="rounded-lg border border-[var(--dashboard-table-line)] bg-[color-mix(in_srgb,var(--dashboard-table-line)_12%,transparent)] p-4">
                  <p className="text-sm leading-6 text-panel-copy">{outcomeFeedback.accountability_note}</p>
                  <p className="mt-2 text-sm leading-6 text-panel-muted">{outcomeFeedback.observed_outcome.detail}</p>
                </div>

                {outcomeFeedback.preparedness_action_evidence ? (
                  <div className="space-y-4 rounded-lg border border-[var(--dashboard-table-line)] bg-[color-mix(in_srgb,var(--dashboard-table-line)_12%,transparent)] px-4 py-4">
                    <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
                      <div>
                        <p className="text-sm font-semibold text-panel-strong">Preparedness action outcome history</p>
                        <p className="mt-1 text-sm text-panel-muted">
                          Ledger actions linked to this ward outcome window.
                        </p>
                      </div>
                      {outcomeFeedback.preparedness_action_evidence.missed_action_review.review_required ? (
                        <StatusBadge tone="danger" className="w-max rounded-full px-3 py-1 tracking-[0.14em]">
                          Missed action review
                        </StatusBadge>
                      ) : null}
                    </div>

                    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
                      {[
                        ["Actions", String(outcomeFeedback.preparedness_action_evidence.summary.total_count)],
                        ["Completed", String(outcomeFeedback.preparedness_action_evidence.summary.completed_count)],
                        ["Overdue", String(outcomeFeedback.preparedness_action_evidence.summary.overdue_count)],
                        ["First completion", formatHours(outcomeFeedback.preparedness_action_evidence.response_time_measurements.hours_to_first_completion)],
                      ].map(([label, value]) => (
                        <div key={label} className="rounded-lg border border-[var(--dashboard-table-line)] p-4">
                          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted">{label}</p>
                          <p className="mt-2 text-sm font-semibold text-panel-strong">{value}</p>
                        </div>
                      ))}
                    </div>

                    {outcomeFeedback.preparedness_action_evidence.action_history.length ? (
                      <div className="space-y-4">
                        {outcomeFeedback.preparedness_action_evidence.action_history.slice(0, 4).map((action) => (
                          <div
                            key={action.public_id}
                            className="rounded-lg border border-[var(--dashboard-table-line)] p-4"
                          >
                            <div className="flex flex-wrap items-center gap-2">
                              <StatusBadge
                                tone={getOutcomeActionTone(action.outcome_status)}
                                className="rounded-full px-3 py-1 tracking-[0.14em]"
                              >
                                {formatFeedbackState(action.outcome_status)}
                              </StatusBadge>
                              <span className="text-sm font-semibold text-panel-strong">{action.action_type_label}</span>
                            </div>
                            <p className="mt-2 text-sm text-panel-muted">
                              Completed: {formatOperationalTime(action.completed_at)} · Owner:{" "}
                              {action.assigned_to_username || action.assigned_to_team || "Unassigned"}
                            </p>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="text-sm text-panel-muted">{outcomeFeedback.preparedness_action_evidence.missed_action_review.detail}</p>
                    )}

                    {outcomeFeedback.preparedness_action_evidence.false_alert_review_context.review_required ? (
                      <div className="rounded-lg border border-[color-mix(in_srgb,var(--warning)_20%,var(--dashboard-table-line))] bg-[color-mix(in_srgb,var(--warning)_8%,var(--panel))] p-4">
                        <p className="text-sm font-semibold text-panel-strong">False-alert context</p>
                        <p className="mt-1 text-sm text-panel-copy">
                          {outcomeFeedback.preparedness_action_evidence.false_alert_review_context.detail}
                        </p>
                      </div>
                    ) : null}
                  </div>
                ) : null}

                <WardDetailDisclosure
                  title="Response pathway detail"
                  summary={`${outcomeFeedback.summary.recorded_step_count}/${outcomeFeedback.summary.step_count} steps recorded; ${outcomeFeedback.summary.downstream_failure_count} downstream gap${outcomeFeedback.summary.downstream_failure_count === 1 ? "" : "s"}.`}
                  badge={`${outcomeFeedback.summary.recorded_step_count}/${outcomeFeedback.summary.step_count} recorded`}
                  badgeTone={outcomeFeedback.summary.downstream_failure_count > 0 ? "danger" : outcomeFeedback.summary.in_progress_step_count > 0 ? "warning" : "success"}
                >
                  <div className="grid gap-4 lg:grid-cols-3">
                    {outcomeFeedback.steps.map((step) => (
                      <div
                        key={step.key}
                        className="rounded-lg border border-[var(--dashboard-table-line)] bg-[color-mix(in_srgb,var(--dashboard-table-line)_14%,transparent)] p-4"
                      >
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <p className="text-sm font-semibold text-panel-strong">{step.label}</p>
                          <StatusBadge tone={getEvidenceTone(step.tone)} className="rounded-full px-3 py-1 tracking-[0.14em]">
                            {formatFeedbackState(step.status)}
                          </StatusBadge>
                        </div>
                        <p className="mt-2 text-sm leading-6 text-panel-muted">{step.detail}</p>
                      </div>
                    ))}
                  </div>
                </WardDetailDisclosure>

                {outcomeFeedback.review_items.length ? (
                  <div className="space-y-4">
                    <p className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted">Attribution review</p>
                    {outcomeFeedback.review_items.map((item) => (
                      <div
                        key={`${item.category}-${item.title}`}
                        className="rounded-lg border border-[color-mix(in_srgb,var(--warning)_20%,var(--dashboard-table-line))] bg-[color-mix(in_srgb,var(--warning)_8%,var(--panel))] p-4"
                      >
                        <div className="flex flex-wrap items-center gap-2">
                          <StatusBadge tone={item.severity === "high" ? "danger" : "warning"} className="rounded-full px-3 py-1 tracking-[0.14em]">
                            {formatFeedbackState(item.category)}
                          </StatusBadge>
                          <span className="text-sm font-semibold text-panel-strong">{item.title}</span>
                        </div>
                        <p className="mt-2 text-sm leading-6 text-panel-copy">{item.detail}</p>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-sm text-panel-muted">No attribution review items are open for the visible ward outcome window.</p>
                )}
              </div>
            ) : (
              <div className="rounded-lg border border-dashed border-[var(--dashboard-table-line)] bg-[color-mix(in_srgb,var(--dashboard-table-line)_16%,transparent)] px-4 py-4">
                <p className="text-sm font-semibold text-panel-strong">Outcome feedback is not available yet.</p>
                <p className="mt-1 text-sm text-panel-muted">Alert-to-action attribution appears when ward evidence includes response and observed outcome records.</p>
              </div>
            )}
          </Card>
          ) : null}

          {activeTab === "response" ? (
          <Card className="space-y-6 p-6">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
              <div className="flex items-center gap-4">
                <span className="inline-flex size-11 items-center justify-center rounded-lg bg-[color-mix(in_srgb,var(--dashboard-sidebar-title)_12%,white)] text-brand dark:bg-[color-mix(in_srgb,var(--dashboard-sidebar-title)_20%,transparent)]">
                  <ClipboardCheck className="size-5" aria-hidden="true" />
                </span>
                <div className="space-y-1">
                  <h3 className="text-xl font-semibold text-panel-strong">Response execution</h3>
                  <p className="text-sm text-panel-muted">Alert handling, preparedness work, and CHV follow-through for this ward.</p>
                </div>
              </div>
              {outcomeFeedback ? (
                <StatusBadge
                  tone={outcomeFeedback.summary.downstream_failure_count > 0 ? "danger" : outcomeFeedback.summary.review_item_count > 0 ? "warning" : "success"}
                  className="w-max rounded-full px-3 py-1 tracking-[0.14em]"
                >
                  {formatFeedbackState(outcomeFeedback.response_quality_state)}
                </StatusBadge>
              ) : null}
            </div>

            {isLoading ? (
              <LoadingBlocks count={4} />
            ) : (
              <div className="space-y-6">
                <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
                  {[
                    ["Alert records", detail ? String(detail.relatedAlerts.length) : "0"],
                    ["Active actions", String(preparednessActionSummary.active)],
                    ["Overdue actions", String(preparednessActionSummary.overdue)],
                    ["Active CHV requests", chvActionStatus ? String(chvActionStatus.summary.active_request_count) : "0"],
                  ].map(([label, value]) => (
                    <div
                      key={label}
                      className="rounded-lg border border-[var(--dashboard-table-line)] bg-[color-mix(in_srgb,var(--dashboard-table-line)_18%,transparent)] p-4"
                    >
                      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted">{label}</p>
                      <p className="mt-2 text-lg font-semibold text-panel-strong">{value}</p>
                    </div>
                  ))}
                </div>

                <section className="space-y-4">
                  <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                    <div>
                      <h4 className="text-base font-semibold text-panel-strong">Recent alerts</h4>
                      <p className="mt-1 text-sm text-panel-muted">Ward-linked delivery activity and interpretation context.</p>
                    </div>
                    <Link
                      href="/alerts"
                      className="inline-flex items-center gap-2 text-sm font-semibold text-brand transition hover:text-[var(--login-link-hover)]"
                    >
                      View full alert history
                      <ChevronRight className="size-4" aria-hidden="true" />
                    </Link>
                  </div>

                  {detail && detail.relatedAlerts.length > 0 ? (
                    <div className="grid gap-4 xl:grid-cols-2">
                      {detail.relatedAlerts.slice(0, 4).map((alert) => (
                        <article
                          key={alert.id}
                          className="rounded-lg border border-[var(--dashboard-table-line)] bg-[color-mix(in_srgb,var(--dashboard-table-line)_18%,transparent)] p-4"
                        >
                          <div className="flex flex-wrap items-center gap-2">
                            <strong className="text-sm font-semibold text-panel-strong">
                              {`${detail.riskLevel === "UNKNOWN" ? "Ward-linked" : formatRiskLevel(detail.riskLevel)} alert`} · {formatRelativeMinutes(alert.created_at)}
                            </strong>
                            <StatusBadge tone={getAlertTone(alert)} className="rounded-full px-3 py-1 tracking-[0.14em]">
                              {alert.status}
                            </StatusBadge>
                          </div>
                          <p className="mt-2 text-sm text-panel-copy">{getAlertSummary(alert)}</p>
                          <details className="mt-2 text-sm text-panel-muted">
                            <summary className="cursor-pointer list-none font-medium text-panel-copy">View alert details</summary>
                            <div className="mt-2 space-y-1">
                              <p>
                                Risk score: {typeof alert.risk_score === "number" ? `${Math.round(normalizeRiskScore(alert.risk_score))}/100` : "Unavailable"}
                              </p>
                              <p>Alert message: {getAlertHeadline(alert)}</p>
                            </div>
                          </details>
                        </article>
                      ))}
                    </div>
                  ) : (
                    <div className="rounded-lg border border-dashed border-[var(--dashboard-table-line)] bg-[color-mix(in_srgb,var(--dashboard-table-line)_16%,transparent)] px-4 py-4">
                      <p className="text-sm font-semibold text-panel-strong">No recent alerts for this ward</p>
                      <p className="mt-1 text-sm text-panel-muted">
                        {detail?.primaryCtaKind === "OPEN_TRIGGER_FLOW" || detail?.primaryCtaKind === "REVIEW_TRIGGER"
                          ? canTriggerFromPage
                            ? detail.primaryCtaKind === "REVIEW_TRIGGER"
                              ? "Review trigger if guided follow-up is still needed."
                              : "Open trigger flow if a guided response is still needed."
                            : "Review alert history or coordinate with an authorized operator if a guided response is still needed."
                          : "Review full alert history if you need older ward-linked alert activity."}
                      </p>
                    </div>
                  )}
                </section>

                <section className="space-y-4">
                  <div>
                    <h4 className="text-base font-semibold text-panel-strong">Preparedness actions</h4>
                    <p className="mt-1 text-sm text-panel-muted">Ward-linked response tasks and lifecycle state.</p>
                  </div>

                  {preparednessActions.length ? (
                    <div className="space-y-4">
                      <div className="grid gap-4 sm:grid-cols-4">
                        {[
                          ["Active", String(preparednessActionSummary.active)],
                          ["Overdue", String(preparednessActionSummary.overdue)],
                          ["Blocked", String(preparednessActionSummary.blocked)],
                          ["Completed", String(preparednessActionSummary.completed)],
                        ].map(([label, value]) => (
                          <div
                            key={label}
                            className="rounded-lg border border-[var(--dashboard-table-line)] bg-[color-mix(in_srgb,var(--dashboard-table-line)_16%,transparent)] p-4"
                          >
                            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted">{label}</p>
                            <p className="mt-2 text-sm font-semibold text-panel-strong">{value}</p>
                          </div>
                        ))}
                      </div>

                      <div className="grid gap-4 xl:grid-cols-2">
                        {preparednessActions.slice(0, 4).map((action) => (
                          <article
                            key={action.public_id}
                            className="rounded-lg border border-[var(--dashboard-table-line)] bg-[color-mix(in_srgb,var(--dashboard-table-line)_18%,transparent)] p-4"
                          >
                            <div className="flex flex-wrap items-center gap-2">
                              <StatusBadge
                                tone={getPreparednessActionTone(action)}
                                className="rounded-full px-3 py-1 tracking-[0.14em]"
                              >
                                {toTitleCase(action.status)}
                              </StatusBadge>
                              <span className="text-sm font-semibold text-panel-strong">
                                {PREPAREDNESS_ACTION_TYPE_LABELS[action.action_type]}
                              </span>
                            </div>
                            <p className="mt-2 text-sm leading-6 text-panel-copy">
                              Owner: {action.assigned_to_username || action.assigned_to_team || "Unassigned"}
                            </p>
                            <p className="text-sm leading-6 text-panel-muted">
                              Due: {formatOperationalTime(action.due_at)}
                            </p>
                            {action.events.length ? (
                              <WardDetailDisclosure
                                title="Latest lifecycle events"
                                summary={`${action.events.length} event${action.events.length === 1 ? "" : "s"} recorded; latest ${toTitleCase(action.events[action.events.length - 1]?.event_type ?? "event")}.`}
                                badge={`${action.events.length} event${action.events.length === 1 ? "" : "s"}`}
                                className="mt-4"
                                bodyClassName="pt-3"
                              >
                                <ol className="mt-2 space-y-2">
                                  {action.events.slice().reverse().slice(0, 2).map((event) => (
                                    <li key={event.public_id} className="flex gap-2 text-sm">
                                      <span className="mt-2 size-1.5 shrink-0 rounded-full bg-brand" aria-hidden="true" />
                                      <span className="min-w-0">
                                        <span className="font-semibold text-panel-strong">{toTitleCase(event.event_type)}</span>
                                        <span className="text-panel-muted">
                                          {" "}
                                          {formatOperationalTime(event.created_at)}
                                        </span>
                                        {event.detail ? <span className="block text-panel-copy">{event.detail}</span> : null}
                                      </span>
                                    </li>
                                  ))}
                                </ol>
                              </WardDetailDisclosure>
                            ) : null}
                          </article>
                        ))}
                      </div>

                      <Link
                        href={`/preparedness-actions?ward_id=${detail?.wardId ?? wardId}`}
                        className="inline-flex items-center gap-2 text-sm font-semibold text-brand transition hover:text-[var(--login-link-hover)]"
                      >
                        Open ward action queue
                        <ChevronRight className="size-4" aria-hidden="true" />
                      </Link>
                    </div>
                  ) : (
                    <div className="rounded-lg border border-dashed border-[var(--dashboard-table-line)] bg-[color-mix(in_srgb,var(--dashboard-table-line)_16%,transparent)] px-4 py-4">
                      <p className="text-sm font-semibold text-panel-strong">No preparedness actions linked yet</p>
                      <p className="mt-1 text-sm text-panel-muted">Response work will appear here when alert, CHV, or facility workflows create ledger tasks.</p>
                    </div>
                  )}
                </section>

                <section className="space-y-4">
                  <div>
                    <h4 className="text-base font-semibold text-panel-strong">CHV action status</h4>
                    <p className="mt-1 text-sm text-panel-muted">Field follow-through linked back to alert records.</p>
                  </div>

                  {chvActionStatus ? (
                    <div className="space-y-4">
                      <div className="grid gap-4 sm:grid-cols-3">
                        {[
                          ["Latest status", toTitleCase(chvActionStatus.summary.latest_status)],
                          ["Active requests", String(chvActionStatus.summary.active_request_count)],
                          ["Linked alerts", String(chvActionStatus.summary.linked_alert_count)],
                        ].map(([label, value]) => (
                          <div
                            key={label}
                            className="rounded-lg border border-[var(--dashboard-table-line)] bg-[color-mix(in_srgb,var(--dashboard-table-line)_16%,transparent)] p-4"
                          >
                            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted">{label}</p>
                            <p className="mt-2 text-sm font-semibold text-panel-strong">{value}</p>
                          </div>
                        ))}
                      </div>

                      {chvActionStatus.requests.length ? (
                        <div className="grid gap-4 xl:grid-cols-2">
                          {chvActionStatus.requests.slice(0, 3).map((request) => (
                            <article
                              key={request.public_id}
                              className="rounded-lg border border-[var(--dashboard-table-line)] bg-[color-mix(in_srgb,var(--dashboard-table-line)_18%,transparent)] p-4"
                            >
                              <div className="flex flex-wrap items-center gap-2">
                                <StatusBadge
                                  tone={request.status === "RESOLVED" ? "success" : request.status === "CANCELLED" || request.status === "REJECTED" ? "danger" : "warning"}
                                  className="rounded-full px-3 py-1 tracking-[0.14em]"
                                >
                                  {request.status}
                                </StatusBadge>
                                <span className="text-sm font-semibold text-panel-strong">{request.priority} priority</span>
                              </div>
                              <p className="mt-2 text-sm leading-6 text-panel-copy">
                                Assignments: {request.assignment_counts.active} active, {request.assignment_counts.completed} completed.
                              </p>
                              <p className="text-sm leading-6 text-panel-muted">
                                Linked alerts: {request.linked_alert_public_ids.length ? request.linked_alert_public_ids.join(", ") : "None linked"}
                              </p>
                            </article>
                          ))}
                        </div>
                      ) : (
                        <div className="rounded-lg border border-dashed border-[var(--dashboard-table-line)] bg-[color-mix(in_srgb,var(--dashboard-table-line)_16%,transparent)] px-4 py-4">
                          <p className="text-sm font-semibold text-panel-strong">No CHV action request linked yet</p>
                          <p className="mt-1 text-sm text-panel-muted">Create or link a CHV coverage request after alert review when field follow-up is needed.</p>
                        </div>
                      )}
                    </div>
                  ) : (
                    <p className="text-sm text-panel-muted">No CHV action evidence is available for this ward.</p>
                  )}
                </section>

                {outcomeFeedback?.review_items.length ? (
                  <WardDetailDisclosure
                    title="Response gaps"
                    summary={`${outcomeFeedback.review_items.length} review item${outcomeFeedback.review_items.length === 1 ? "" : "s"} need attention before response can be considered closed.`}
                    badge={`${outcomeFeedback.review_items.length} gap${outcomeFeedback.review_items.length === 1 ? "" : "s"}`}
                    badgeTone={outcomeFeedback.summary.downstream_failure_count > 0 ? "danger" : "warning"}
                  >
                    <div className="space-y-3">
                      {outcomeFeedback.review_items.map((item) => (
                        <div
                          key={`${item.category}-${item.title}`}
                          className="rounded-lg border border-[color-mix(in_srgb,var(--warning)_20%,var(--dashboard-table-line))] bg-[color-mix(in_srgb,var(--warning)_8%,var(--panel))] p-4"
                        >
                          <div className="flex flex-wrap items-center gap-2">
                            <StatusBadge tone={item.severity === "high" ? "danger" : "warning"} className="rounded-full px-3 py-1 tracking-[0.14em]">
                              {formatFeedbackState(item.category)}
                            </StatusBadge>
                            <span className="text-sm font-semibold text-panel-strong">{item.title}</span>
                          </div>
                          <p className="mt-2 text-sm leading-6 text-panel-copy">{item.detail}</p>
                        </div>
                      ))}
                    </div>
                  </WardDetailDisclosure>
                ) : null}
              </div>
            )}
          </Card>
          ) : null}

          {activeTab === "history" || activeTab === "situation" ? (
          <section className="grid gap-6">
            {activeTab === "history" ? (
            <Card className="space-y-6 p-6">
              <div className="flex items-start gap-4">
                <span className="inline-flex size-11 shrink-0 items-center justify-center rounded-lg bg-[color-mix(in_srgb,var(--dashboard-sidebar-title)_12%,white)] text-brand dark:bg-[color-mix(in_srgb,var(--dashboard-sidebar-title)_20%,transparent)]">
                  <MapPinned className="size-5" aria-hidden="true" />
                </span>
                <div className="space-y-1">
                  <h3 className="pt-1 text-xl font-semibold text-panel-strong">Ward context</h3>
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
            ) : null}

            {activeTab === "situation" ? (
            <Card className="space-y-6 p-6">
              <div className="flex items-start gap-4">
                <span className="inline-flex size-11 shrink-0 items-center justify-center rounded-lg bg-[color-mix(in_srgb,var(--dashboard-sidebar-title)_12%,white)] text-brand dark:bg-[color-mix(in_srgb,var(--dashboard-sidebar-title)_20%,transparent)]">
                  <MapPinned className="size-5" aria-hidden="true" />
                </span>
                <div className="space-y-1">
                  <h3 className="pt-1 text-xl font-semibold text-panel-strong">Spatial context</h3>
                  <p className="text-sm text-panel-muted">{getSpatialEvidenceHeadline(spatialEvidence)}</p>
                </div>
              </div>

              {isLoading ? (
                <LoadingBlocks count={3} className="h-12 rounded-lg bg-[color-mix(in_srgb,var(--dashboard-table-line)_55%,transparent)]" />
              ) : spatialEvidence ? (
                <div className="space-y-4">
                  <div className="grid gap-4 sm:grid-cols-2">
                    {[
                      ["Neighboring high-risk wards", String(spatialSummary?.high_risk_neighbor_count ?? 0)],
                      ["Neighboring outbreak labels", String(spatialSummary?.active_outbreak_neighbor_count ?? 0)],
                      ["Facility pressure", spatialSummary?.max_catchment_pressure_score == null ? "Unavailable" : `${spatialSummary.max_catchment_pressure_score}/100`],
                      ["Water proximity", spatialSummary?.water_proximity_available ? formatSpatialPercent(spatialSummary.water_proximity_value) : "Unavailable"],
                    ].map(([label, value]) => (
                      <div
                        key={label}
                        className="rounded-lg border border-[var(--dashboard-table-line)] bg-[color-mix(in_srgb,var(--dashboard-table-line)_18%,transparent)] p-4"
                      >
                        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted">{label}</p>
                        <p className="mt-2 text-sm font-semibold text-panel-strong">{value}</p>
                      </div>
                    ))}
                  </div>

                  <div className="overflow-hidden rounded-lg border border-panel-table-wrap bg-[color-mix(in_srgb,var(--dashboard-table-line)_12%,transparent)] p-2">
                    <div className="flex flex-col gap-4 rounded-lg border border-panel-table-wrap bg-panel p-4">
                      <div className="flex items-center justify-between gap-4 text-xs uppercase tracking-[0.18em] text-panel-subtle">
                        <span>Spatial graph</span>
                        <span>{spatialMapFeatures.length ? `${spatialMapFeatures.length} mapped wards` : "No geometry"}</span>
                      </div>
                      <div className="h-64 overflow-hidden rounded-lg border border-panel-table-wrap bg-white/60 p-2 dark:bg-panel/70">
                        {spatialMapFeatures.length ? (
                          <MigoriWardMap
                            features={spatialMapFeatures}
                            selectedWardCode={detail?.wardMapFeature?.properties.ward_code ?? null}
                            focusHighRisk={highRiskSpatialNeighbors.length > 0}
                            onSelectWard={() => undefined}
                          />
                        ) : (
                          <div className="flex h-full items-center justify-center text-center text-sm text-panel-muted">
                            Spatial graph exists for the ward, but matching map geometry is not available.
                          </div>
                        )}
                      </div>
                      <div className="flex flex-wrap gap-2">
                        {detail?.wardMapFeature ? (
                          <span className="inline-flex w-max items-center gap-2 rounded-full bg-[color-mix(in_srgb,var(--brand)_10%,white)] px-3 py-1.5 text-xs font-semibold text-panel-strong dark:bg-[color-mix(in_srgb,var(--brand)_18%,transparent)]">
                            <span className="size-2 rounded-full bg-brand" />
                            {detail.wardName}
                          </span>
                        ) : null}
                        {highRiskSpatialNeighbors.length ? (
                          <span className="inline-flex w-max items-center gap-2 rounded-full bg-[color-mix(in_srgb,var(--danger)_10%,white)] px-3 py-1.5 text-xs font-semibold text-[color:var(--danger)] dark:bg-[color-mix(in_srgb,var(--danger)_18%,transparent)]">
                            <span className="size-2 rounded-full bg-[color:var(--danger)]" />
                            High-risk neighbors
                          </span>
                        ) : null}
                      </div>
                    </div>
                  </div>

                  <WardDetailDisclosure
                    title="Spillover signals"
                    summary={
                      spatialEvidence.neighbors.length
                        ? `${spatialSummary?.high_risk_neighbor_count ?? 0} high-risk neighboring ward${(spatialSummary?.high_risk_neighbor_count ?? 0) === 1 ? "" : "s"}; ${spatialSummary?.active_outbreak_neighbor_count ?? 0} outbreak-labeled neighbor${(spatialSummary?.active_outbreak_neighbor_count ?? 0) === 1 ? "" : "s"}.`
                        : "No generated neighbor relationships are available for this ward."
                    }
                    badge={
                      (spatialSummary?.high_risk_neighbor_count ?? 0) > 0
                        ? "High-risk neighbors"
                        : spatialEvidence.neighbors.some((neighbor) => neighbor.is_approximate_relationship)
                          ? "Approximate links"
                          : `${spatialEvidence.neighbors.length} neighbor${spatialEvidence.neighbors.length === 1 ? "" : "s"}`
                    }
                    badgeTone={
                      (spatialSummary?.high_risk_neighbor_count ?? 0) > 0
                        ? "danger"
                        : spatialEvidence.neighbors.some((neighbor) => neighbor.is_approximate_relationship)
                          ? "warning"
                          : "default"
                    }
                  >
                    <div className="space-y-4">
                      {spatialEvidence.neighbors.length ? (
                        spatialEvidence.neighbors.slice(0, 4).map((neighbor) => (
                          <div
                            key={neighbor.ward_id}
                            className="rounded-lg border border-[var(--dashboard-table-line)] bg-[color-mix(in_srgb,var(--dashboard-table-line)_14%,transparent)] p-4"
                          >
                            <div className="flex flex-wrap items-center justify-between gap-2">
                              <span className="text-sm font-semibold text-panel-strong">{neighbor.ward_name}</span>
                              <div className="flex flex-wrap items-center gap-2">
                                {neighbor.is_approximate_relationship ? (
                                  <StatusBadge tone="warning" className="rounded-full px-3 py-1 tracking-[0.14em]">
                                    Approximate link
                                  </StatusBadge>
                                ) : null}
                                <StatusBadge tone={getRiskBadgeTone(neighbor.risk_level ?? "UNKNOWN")} className="rounded-full px-3 py-1 tracking-[0.14em]">
                                  {neighbor.risk_level ?? "UNKNOWN"}
                                </StatusBadge>
                              </div>
                            </div>
                            <p className="mt-2 text-sm leading-6 text-panel-muted">
                              {neighbor.relationship_labels.join(", ") || "Relationship"} · Risk {formatRiskScore(neighbor.risk_score)} · Distance {formatSpatialDistance(neighbor.distance, neighbor.distance_unit)}
                            </p>
                            {neighbor.approximation_notice ? (
                              <p className="mt-1 text-sm leading-6 text-panel-muted">{neighbor.approximation_notice}</p>
                            ) : null}
                            {neighbor.active_outbreak_label || neighbor.surveillance_record_count_28d > 0 ? (
                              <p className="mt-1 text-sm leading-6 text-panel-copy">
                                {neighbor.active_outbreak_label ? "Active outbreak label" : "Surveillance signal"} · {neighbor.suspected_cases_28d} suspected in 28 days · trend {neighbor.suspected_case_trend_14d_delta >= 0 ? "+" : ""}{neighbor.suspected_case_trend_14d_delta}
                              </p>
                            ) : null}
                          </div>
                        ))
                      ) : (
                        <p className="rounded-lg border border-dashed border-[var(--dashboard-table-line)] p-4 text-sm text-panel-muted">
                          No generated neighbor relationships are available for this ward.
                        </p>
                      )}
                    </div>
                  </WardDetailDisclosure>

                  <WardDetailDisclosure
                    title="Catchment pressure"
                    summary={
                      spatialEvidence.facility_catchments.length
                        ? `${spatialEvidence.facility_catchments.length} catchment record${spatialEvidence.facility_catchments.length === 1 ? "" : "s"}; max pressure ${spatialSummary?.max_catchment_pressure_score == null ? "unavailable" : `${spatialSummary.max_catchment_pressure_score}/100`}.`
                        : "No facility catchment records cover this ward yet."
                    }
                    badge={spatialSummary?.approximate_catchment_count ? "Approximate" : `${spatialEvidence.facility_catchments.length} record${spatialEvidence.facility_catchments.length === 1 ? "" : "s"}`}
                    badgeTone={spatialSummary?.approximate_catchment_count ? "warning" : "default"}
                  >
                    <div className="space-y-4">
                      {spatialEvidence.facility_catchments.length ? (
                        spatialEvidence.facility_catchments.slice(0, 3).map((catchment) => (
                          <div
                            key={catchment.catchment_id}
                            className="rounded-lg border border-[var(--dashboard-table-line)] bg-[color-mix(in_srgb,var(--dashboard-table-line)_14%,transparent)] p-4"
                          >
                            <div className="flex flex-wrap items-center justify-between gap-2">
                              <span className="text-sm font-semibold text-panel-strong">{catchment.facility_name}</span>
                              <StatusBadge
                                tone={getSpatialReadinessTone(catchment.projected_pressure_score)}
                                className="rounded-full px-3 py-1 tracking-[0.14em]"
                              >
                                {catchment.projected_pressure_score == null ? "No forecast" : `${catchment.projected_pressure_score}/100`}
                              </StatusBadge>
                            </div>
                            <p className="mt-2 text-sm leading-6 text-panel-muted">
                              {catchment.catchment_method_label} · {catchment.covered_ward_names.length} covered ward{catchment.covered_ward_names.length === 1 ? "" : "s"} · {catchment.projected_readiness_label}
                            </p>
                          </div>
                        ))
                      ) : (
                        <p className="rounded-lg border border-dashed border-[var(--dashboard-table-line)] p-4 text-sm text-panel-muted">
                          No facility catchment records cover this ward yet.
                        </p>
                      )}
                    </div>
                  </WardDetailDisclosure>

                  <div className="grid gap-4 sm:grid-cols-2">
                    <div className="rounded-lg border border-[var(--dashboard-table-line)] p-4">
                      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted">Nearest facility</p>
                      <p className="mt-2 text-sm font-semibold text-panel-strong">
                        {spatialEvidence.nearest_facility?.facility_name ?? "Unavailable"}
                      </p>
                      <p className="mt-1 text-sm text-panel-muted">
                        {formatSpatialDistance(spatialEvidence.nearest_facility?.distance, spatialEvidence.nearest_facility?.distance_unit)}
                      </p>
                    </div>
                    <div className="rounded-lg border border-[var(--dashboard-table-line)] p-4">
                      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted">Water proximity</p>
                      <p className="mt-2 text-sm font-semibold text-panel-strong">
                        {spatialEvidence.water_proximity.source_available ? formatSpatialPercent(spatialEvidence.water_proximity.value) : "Unavailable"}
                      </p>
                      <p className="mt-1 text-sm text-panel-muted">{spatialEvidence.water_proximity.display_caveat}</p>
                    </div>
                  </div>

                  {spatialEvidence.caveats.length ? (
                    <WardDetailDisclosure
                      title="Spatial caveats"
                      summary={`${spatialEvidence.caveats.length} caveat${spatialEvidence.caveats.length === 1 ? "" : "s"} require review before using spatial signals as operational truth.`}
                      badge={`${spatialEvidence.caveats.length} caveat${spatialEvidence.caveats.length === 1 ? "" : "s"}`}
                      badgeTone="warning"
                    >
                      <div className="space-y-2">
                        {spatialEvidence.caveats.map((caveat) => (
                          <div
                            key={caveat}
                            className="flex items-start gap-2 rounded-lg border border-[color-mix(in_srgb,var(--warning)_20%,var(--dashboard-table-line))] bg-[color-mix(in_srgb,var(--warning)_8%,var(--panel))] p-4"
                          >
                            <AlertTriangle className="mt-0.5 size-4 shrink-0 text-[color:var(--warning)]" aria-hidden="true" />
                            <p className="text-sm leading-6 text-panel-copy">{caveat}</p>
                          </div>
                        ))}
                      </div>
                    </WardDetailDisclosure>
                  ) : null}
                </div>
              ) : (
                <div className="rounded-lg border border-dashed border-[var(--dashboard-table-line)] bg-[color-mix(in_srgb,var(--dashboard-table-line)_16%,transparent)] px-4 py-4">
                  <p className="text-sm font-semibold text-panel-strong">Spatial evidence is not available yet.</p>
                  <p className="mt-1 text-sm text-panel-muted">Spatial context will appear once relationship and catchment records exist for this ward.</p>
                </div>
              )}
            </Card>
            ) : null}
          </section>
          ) : null}
        </div>

        <WardActionRail>
          <Card className="space-y-6 p-6">
            <div className="flex items-center gap-4">
              <span className="inline-flex size-11 items-center justify-center rounded-lg bg-[color-mix(in_srgb,var(--dashboard-sidebar-title)_12%,white)] text-brand dark:bg-[color-mix(in_srgb,var(--dashboard-sidebar-title)_20%,transparent)]">
                <Zap className="size-5" aria-hidden="true" />
              </span>
              <div className="space-y-1">
                <h3 className="text-xl font-semibold text-panel-strong">Recommended action</h3>
                <p className="text-sm text-panel-muted">The next truthful operator step for this ward.</p>
              </div>
            </div>

            {isLoading ? (
              <LoadingBlocks count={3} />
            ) : detail ? (
              <div className="space-y-4">
                <div className="rounded-lg border border-[var(--dashboard-table-line)] bg-[color-mix(in_srgb,var(--dashboard-table-line)_20%,transparent)] px-4 py-4">
                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted">Primary action</p>
                  <p className="mt-2 text-base font-semibold text-panel-strong">
                    {recommendedActionState?.primaryAction}
                  </p>
                </div>

                <div className="rounded-lg border border-[var(--dashboard-table-line)] bg-[color-mix(in_srgb,var(--dashboard-table-line)_16%,transparent)] px-4 py-4">
                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted">Why</p>
                  <p className="mt-2 text-sm leading-6 text-panel-copy">{recommendedActionState?.why}</p>
                </div>

                {actionRailOperatingNote ? (
                  <div className="rounded-lg border border-[var(--dashboard-table-line)] bg-[color-mix(in_srgb,var(--dashboard-table-line)_14%,transparent)] px-4 py-4">
                    <p className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted">Operating note</p>
                    <p className="mt-2 text-sm leading-6 text-panel-copy">{actionRailOperatingNote}</p>
                  </div>
                ) : null}

                <div className="rounded-lg border border-[var(--dashboard-table-line)] bg-[color-mix(in_srgb,var(--dashboard-table-line)_16%,transparent)] px-4 py-4">
                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted">Next steps</p>
                  <div className="mt-4 space-y-4">
                    {recommendedActionState?.nextSteps.map((step, index) => (
                      <div key={step} className="flex items-start gap-4">
                        <span className="inline-flex size-7 shrink-0 items-center justify-center rounded-full bg-[color-mix(in_srgb,var(--brand)_10%,white)] text-xs font-semibold text-brand">
                          {index + 1}
                        </span>
                        <p className="pt-1 text-sm font-medium text-panel-strong">{step}</p>
                      </div>
                    ))}
                  </div>
                </div>

                {detail.workflow?.expected_operational_effect ? (
                  <div className="rounded-lg border border-[color-mix(in_srgb,var(--success)_18%,var(--dashboard-table-line))] bg-[color-mix(in_srgb,var(--success)_8%,var(--panel))] px-4 py-4">
                    <p className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted">Expected effect</p>
                    <p className="mt-2 text-sm leading-6 text-panel-copy">{detail.workflow.expected_operational_effect}</p>
                  </div>
                ) : null}

                {recommendations.length > 0 ? (
                  <div className="space-y-4">
                    <p className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted">Supporting checks</p>
                    {recommendations.map((recommendation) => (
                      <div
                        key={recommendation.text}
                        className="flex items-start gap-4 rounded-lg border border-[var(--dashboard-table-line)] p-4"
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

          {activeTab === "evidence" ? (
          <Card className="space-y-6 p-6">
            <div className="flex items-center gap-4">
              <span className="inline-flex size-11 items-center justify-center rounded-lg bg-[color-mix(in_srgb,var(--warning)_12%,white)] text-[color:var(--warning)] dark:bg-[color-mix(in_srgb,var(--warning)_20%,transparent)]">
                <ClipboardCheck className="size-5" aria-hidden="true" />
              </span>
              <div className="space-y-1">
                <h3 className="text-xl font-semibold text-panel-strong">Alert candidate review</h3>
                <p className="text-sm text-panel-muted">Decision-policy state before response work is created or repeated.</p>
              </div>
            </div>

            {isLoading ? (
              <LoadingBlocks count={3} />
            ) : alertCandidateReview ? (
              <div className="space-y-4">
                <div className="rounded-lg border border-[var(--dashboard-table-line)] bg-[color-mix(in_srgb,var(--dashboard-table-line)_18%,transparent)] px-4 py-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <StatusBadge
                      tone={alertCandidateReview.review_state === "routine_monitoring" ? "success" : "warning"}
                      className="rounded-full px-3 py-1 tracking-[0.14em]"
                    >
                      {formatReviewState(alertCandidateReview.review_state)}
                    </StatusBadge>
                    {alertCandidateReview.policy_version ? (
                      <span className="text-xs font-semibold uppercase tracking-[0.14em] text-panel-muted">
                        {alertCandidateReview.policy_version}
                      </span>
                    ) : null}
                  </div>
                  <dl className="mt-4 grid gap-4">
                    {[
                      ["Decision", toTitleCase(alertCandidateReview.alert_decision || "routine_monitoring")],
                      ["Automatic alert", alertCandidateReview.automatic_alert_allowed ? "Allowed by policy" : "Blocked or manual review only"],
                      ["Active alerts", String(alertCandidateReview.active_alert_count)],
                    ].map(([label, value]) => (
                      <div key={label} className="grid gap-1 border-b border-[var(--dashboard-table-line)] pb-3 last:border-b-0 last:pb-0">
                        <dt className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted">{label}</dt>
                        <dd className="text-sm font-medium text-panel-strong">{value}</dd>
                      </div>
                    ))}
                  </dl>
                </div>

                <div className="rounded-lg border border-[var(--dashboard-table-line)] bg-[color-mix(in_srgb,var(--dashboard-table-line)_14%,transparent)] px-4 py-4">
                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted">Recommended review action</p>
                  <p className="mt-2 text-sm leading-6 text-panel-copy">{alertCandidateReview.recommended_action}</p>
                </div>

                {alertCandidateReview.automatic_alert_blockers.length ? (
                  <div className="space-y-2">
                    <p className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted">Policy blockers</p>
                    {alertCandidateReview.automatic_alert_blockers.map((blocker) => (
                      <div key={blocker} className="flex items-start gap-2 rounded-lg border border-[var(--dashboard-table-line)] px-3 py-2">
                        <Eye className="mt-0.5 size-4 shrink-0 text-[color:var(--warning)]" aria-hidden="true" />
                        <p className="text-sm text-panel-copy">{toTitleCase(blocker)}</p>
                      </div>
                    ))}
                  </div>
                ) : null}
              </div>
            ) : (
              <p className="text-sm text-panel-muted">No alert candidate review evidence is available for this ward.</p>
            )}
          </Card>
          ) : null}

          {activeTab === "history" ? (
          <Card className="space-y-6 p-6">
            <div className="flex items-center gap-4">
              <span className="inline-flex size-11 items-center justify-center rounded-lg bg-[color-mix(in_srgb,var(--dashboard-sidebar-title)_12%,white)] text-brand dark:bg-[color-mix(in_srgb,var(--dashboard-sidebar-title)_20%,transparent)]">
                <Bell className="size-5" aria-hidden="true" />
              </span>
              <div className="space-y-1">
                <h3 className="text-xl font-semibold text-panel-strong">Recent alerts</h3>
                <p className="text-sm text-panel-muted">Recent ward-linked alert activity with interpretation context.</p>
              </div>
            </div>

            {isLoading ? (
              <LoadingBlocks count={3} />
            ) : detail && detail.relatedAlerts.length > 0 ? (
              <>
                <div className="space-y-4">
                {detail.relatedAlerts.slice(0, 4).map((alert) => (
                  <article
                    key={alert.id}
                    className="rounded-lg border border-[var(--dashboard-table-line)] bg-[color-mix(in_srgb,var(--dashboard-table-line)_28%,transparent)] px-4 py-4"
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
                      <p className="text-sm text-panel-copy">{getAlertSummary(alert)}</p>
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
              <div className="rounded-lg border border-dashed border-[var(--dashboard-table-line)] bg-[color-mix(in_srgb,var(--dashboard-table-line)_16%,transparent)] px-4 py-4">
                <p className="text-sm font-semibold text-panel-strong">No recent alerts for this ward</p>
                <p className="mt-1 text-sm text-panel-muted">
                  {detail?.primaryCtaKind === "OPEN_TRIGGER_FLOW" || detail?.primaryCtaKind === "REVIEW_TRIGGER"
                    ? canTriggerFromPage
                      ? detail.primaryCtaKind === "REVIEW_TRIGGER"
                        ? "Review trigger if guided follow-up is still needed."
                        : "Open trigger flow if a guided response is still needed."
                      : "Review alert history or coordinate with an authorized operator if a guided response is still needed."
                    : "Review full alert history if you need older ward-linked alert activity."}
                </p>
              </div>
            )}
          </Card>
          ) : null}

          {activeTab === "history" ? (
          <Card className="space-y-6 p-6">
            <div className="flex items-center gap-4">
              <span className="inline-flex size-11 items-center justify-center rounded-lg bg-[color-mix(in_srgb,var(--dashboard-sidebar-title)_12%,white)] text-brand dark:bg-[color-mix(in_srgb,var(--dashboard-sidebar-title)_20%,transparent)]">
                <Clock3 className="size-5" aria-hidden="true" />
              </span>
              <div className="space-y-1">
                <h3 className="text-xl font-semibold text-panel-strong">Data status</h3>
                <p className="text-sm text-panel-muted">Compact freshness status with optional detail.</p>
              </div>
            </div>

            {isLoading ? (
              <LoadingBlocks count={3} className="h-4 rounded-full bg-[color-mix(in_srgb,var(--dashboard-table-line)_55%,transparent)]" />
            ) : detail ? (
              <details className="group rounded-lg border border-[var(--dashboard-table-line)] bg-[color-mix(in_srgb,var(--dashboard-table-line)_16%,transparent)] px-4 py-4">
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
          ) : null}
        </WardActionRail>
      </section>
    </div>
  );
}
