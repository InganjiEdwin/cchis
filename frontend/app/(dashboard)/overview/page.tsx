"use client";

import { Activity, AlertTriangle, ArrowRight, Bell, CircleAlert, TriangleAlert, TrendingDown, TrendingUp } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { DashboardTopbar } from "@/components/dashboard-topbar";
import { OverviewHotspotMap, type OverviewMapFilter, type OverviewRiskMode } from "@/components/overview-hotspot-map";
import { TriggerAlertPanel } from "@/components/trigger-alert-panel";
import { TriggerReviewDrawer } from "@/components/trigger-review-drawer";
import { Card } from "@/components/ui/card";
import { PageSectionHeader } from "@/components/ui/page-section-header";
import { StatusBadge } from "@/components/ui/status-badge";
import type {
  AlertRecord,
  OverviewDecisionMode,
  OverviewEligibleAction,
  ScenarioSimulationRun,
  OverviewStateModel,
  OverviewTriggeredWard,
  OverviewTriggerEvent,
  WardMapFeature,
} from "@/lib/dashboard";
import { runScenarioSimulationViaBff } from "@/lib/dashboard";
import { useOverviewQuery } from "@/queries/use-overview-query";

function formatStatusLabel(status: AlertRecord["status"]) {
  return status
    .toLowerCase()
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function formatChannelLabel(channel: AlertRecord["channel"]) {
  if (channel === "DASHBOARD") {
    return "System";
  }
  return channel;
}

function normalizeRiskScore(score: number) {
  if (!Number.isFinite(score)) {
    return 0;
  }
  if (score <= 1) {
    return Math.max(0, Math.min(score * 100, 100));
  }
  return Math.max(0, Math.min(score, 100));
}

function formatRiskScore(score: number) {
  if (!Number.isFinite(score)) {
    return "N/A";
  }
  return Math.round(normalizeRiskScore(score)).toString();
}

function formatCompactRelativeMinutes(timestamp: string | null) {
  if (!timestamp) {
    return "No recent update";
  }

  const date = new Date(timestamp);

  if (Number.isNaN(date.getTime())) {
    return "Invalid timestamp";
  }

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
  if (!timestamp) {
    return "No timestamp";
  }

  const date = new Date(timestamp);

  if (Number.isNaN(date.getTime())) {
    return "Invalid timestamp";
  }

  const timeLabel = date.toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });

  return `${timeLabel} (${formatCompactRelativeMinutes(timestamp)})`;
}

function formatRelativeOperationalAge(timestamp: string | null) {
  if (!timestamp) {
    return "No recent update";
  }

  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) {
    return "Invalid timestamp";
  }

  const diffMinutes = Math.max(0, Math.round((Date.now() - date.getTime()) / 60000));
  if (diffMinutes < 1) return "Just now";
  if (diffMinutes < 60) return `${diffMinutes}m ago`;

  const diffHours = Math.round(diffMinutes / 60);
  if (diffHours < 24) return `${diffHours}h ago`;

  const diffDays = Math.round(diffHours / 24);
  return `${diffDays}d ago`;
}

function formatExactOperationalTimestamp(timestamp: string | null) {
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
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatScenarioRiskDelta(baseline: number, simulated: number) {
  const baselineScore = normalizeRiskScore(baseline);
  const simulatedScore = normalizeRiskScore(simulated);
  const delta = Math.round(simulatedScore - baselineScore);

  if (delta === 0) {
    return "No risk change";
  }

  return `${delta > 0 ? "+" : ""}${delta} risk score`;
}

function formatScenarioCaseDelta(baseline: number, simulated: number) {
  const delta = simulated - baseline;
  if (delta === 0) {
    return "No case change";
  }

  return `${delta > 0 ? "+" : ""}${delta} predicted cases`;
}

function formatScenarioTopWardLabel(wardName: string | null | undefined) {
  return wardName && wardName.trim().length > 0 ? wardName : "No standout ward";
}

function formatScenarioDeltaSummary(deltaLabel: string) {
  if (deltaLabel === "No risk change" || deltaLabel === "No case change") {
    return "No visible change";
  }
  return deltaLabel;
}

function normalizeWardKey(value: string | null | undefined) {
  return (value ?? "").trim().toLowerCase();
}

function isOperationallyStaleAlert(timestamp: string | null) {
  if (!timestamp) {
    return false;
  }

  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) {
    return false;
  }

  const ageHours = (Date.now() - date.getTime()) / 3_600_000;
  return ageHours > 48;
}

function getScoreTone(score: number) {
  const normalizedScore = normalizeRiskScore(score);

  if (normalizedScore >= 80)
    return "bg-[color-mix(in_srgb,var(--danger)_18%,var(--dashboard-panel-surface))] text-[color:var(--danger)]";
  if (normalizedScore >= 65)
    return "bg-[color-mix(in_srgb,var(--danger)_16%,var(--dashboard-panel-surface))] text-[color:var(--danger)]";
  if (normalizedScore >= 45)
    return "bg-[color-mix(in_srgb,var(--warning)_18%,var(--dashboard-panel-surface))] text-[color:var(--warning)]";
  if (normalizedScore >= 25)
    return "bg-[color-mix(in_srgb,var(--brand)_16%,var(--dashboard-panel-surface))] text-brand";
  return "bg-[color-mix(in_srgb,var(--success)_18%,var(--dashboard-panel-surface))] text-[color:var(--success)]";
}

function getRiskBadgeTone(level: "LOW" | "MEDIUM" | "HIGH" | null) {
  if (level === "HIGH") return "danger" as const;
  if (level === "MEDIUM") return "warning" as const;
  return "success" as const;
}

function deriveAlertRiskLevel(riskScore: number | null) {
  if (typeof riskScore !== "number" || !Number.isFinite(riskScore)) {
    return "LOW" as const;
  }

  const normalized = normalizeRiskScore(riskScore);
  if (normalized >= 75) return "HIGH" as const;
  if (normalized >= 45) return "MEDIUM" as const;
  return "LOW" as const;
}

function getAlertRiskDotClass(level: "LOW" | "MEDIUM" | "HIGH") {
  if (level === "HIGH") return "bg-[color:var(--danger)]";
  if (level === "MEDIUM") return "bg-[color:var(--warning)]";
  return "bg-[color:var(--success)]";
}

function getOperationalAlertStatusRank(status: AlertRecord["status"]) {
  if (status === "RETRY_PENDING") return 0;
  if (status === "FAILED") return 1;
  if (status === "QUEUED") return 2;
  return 3;
}

type RecentAlertFilter = "ALL" | "RETRY_PENDING" | "DELIVERED" | "HIGH_RISK";

function getAttentionCardClass(level: "LOW" | "MEDIUM" | "HIGH" | null, isPrimary: boolean) {
  const base = "space-y-3 rounded-[1.5rem] p-4 shadow-none";

  if (level === "HIGH") {
    return `${base} border-[color-mix(in_srgb,var(--danger)_26%,var(--dashboard-panel-border))] bg-[linear-gradient(135deg,color-mix(in_srgb,var(--danger)_12%,var(--dashboard-panel-surface)),var(--dashboard-panel-surface))]${isPrimary ? " ring-1 ring-[color:var(--danger)]/20" : ""}`;
  }

  if (level === "MEDIUM") {
    return `${base} border-[color-mix(in_srgb,var(--warning)_26%,var(--dashboard-panel-border))] bg-[linear-gradient(135deg,color-mix(in_srgb,var(--warning)_12%,var(--dashboard-panel-surface)),var(--dashboard-panel-surface))]`;
  }

  return `${base} border-[color-mix(in_srgb,var(--success)_24%,var(--dashboard-panel-border))] bg-[linear-gradient(135deg,color-mix(in_srgb,var(--success)_12%,var(--dashboard-panel-surface)),var(--dashboard-panel-surface))]`;
}

function getMapFilterLabel(filter: OverviewMapFilter) {
  if (filter === "high") return "High risk";
  if (filter === "medium") return "Medium risk";
  if (filter === "low") return "Low risk";
  if (filter === "alerts") return "Active alerts";
  if (filter === "workflow_active") return "Workflow-active wards";
  if (filter === "delivery_concern") return "Delivery concern";
  return "All wards";
}

function getSystemStateSurfaceClass(state: OverviewStateModel["system_state"]) {
  if (state === "action_required") {
    return "border-[color-mix(in_srgb,var(--danger)_24%,white)] bg-[linear-gradient(135deg,color-mix(in_srgb,var(--danger)_9%,white),color-mix(in_srgb,var(--panel)_96%,transparent))] dark:border-[color-mix(in_srgb,var(--danger)_28%,transparent)] dark:bg-[linear-gradient(135deg,color-mix(in_srgb,var(--danger)_16%,transparent),color-mix(in_srgb,var(--panel)_94%,transparent))]";
  }
  if (state === "watch") {
    return "border-[color-mix(in_srgb,var(--warning)_24%,white)] bg-[linear-gradient(135deg,color-mix(in_srgb,var(--warning)_10%,white),color-mix(in_srgb,var(--panel)_96%,transparent))] dark:border-[color-mix(in_srgb,var(--warning)_28%,transparent)] dark:bg-[linear-gradient(135deg,color-mix(in_srgb,var(--warning)_16%,transparent),color-mix(in_srgb,var(--panel)_94%,transparent))]";
  }
  return "border-[color-mix(in_srgb,var(--success)_22%,white)] bg-[linear-gradient(135deg,color-mix(in_srgb,var(--success)_10%,white),color-mix(in_srgb,var(--panel)_96%,transparent))] dark:border-[color-mix(in_srgb,var(--success)_28%,transparent)] dark:bg-[linear-gradient(135deg,color-mix(in_srgb,var(--success)_16%,transparent),color-mix(in_srgb,var(--panel)_94%,transparent))]";
}

function formatSystemStateLabel(state: OverviewStateModel["system_state"]) {
  if (state === "action_required") return "Action Required";
  if (state === "watch") return "Watch";
  return "System Stable";
}

function formatSystemHeartbeatLabel(state: OverviewStateModel["system_state"]) {
  if (state === "action_required") return "Active Triggers";
  if (state === "watch") return "Watch";
  return "Stable";
}

function getSystemStateTone(state: OverviewStateModel["system_state"]) {
  if (state === "action_required") return "danger" as const;
  if (state === "watch") return "warning" as const;
  return "success" as const;
}

function formatTriggerSummaryLine(overviewState: OverviewStateModel | null | undefined) {
  if (!overviewState) {
    return "No wards triggered • No recent trigger • Stable";
  }

  if (overviewState.system_state === "action_required") {
    const triggeredCount = overviewState.trigger_count;
    const triggeredLabel = `${triggeredCount} ward${triggeredCount === 1 ? "" : "s"} triggered`;
    const lastTriggerLabel = overviewState.last_triggered_at
      ? `Last trigger ${formatCompactRelativeMinutes(overviewState.last_triggered_at)}`
      : "No recent trigger";
    return `${triggeredLabel} • ${lastTriggerLabel} • Awaiting action`;
  }

  if (overviewState.system_state === "watch") {
    const watchCount = overviewState.watch_count;
    const watchLabel = `${watchCount} ward${watchCount === 1 ? "" : "s"} under watch`;
    const lastTriggerLabel = overviewState.last_triggered_at
      ? `Last trigger ${formatCompactRelativeMinutes(overviewState.last_triggered_at)}`
      : "No recent trigger";
    return `${watchLabel} • ${lastTriggerLabel} • Review conditions`;
  }

  return "No wards triggered • No recent trigger • Stable";
}

type TriggerSurfaceState = {
  state: "action_required" | "monitoring" | "stable";
  headline: string;
  interpretation: string;
  triggerActiveCount: number;
  deliveryConcernCount: number;
  reviewCount: number;
  showBanner: boolean;
};

function deriveTriggerSurfaceState(args: {
  overviewState: OverviewStateModel | null | undefined;
  triggerReviewQueueCount: number;
  triggerActiveCount: number;
  deliveryConcernCount: number;
}) {
  const { overviewState, triggerReviewQueueCount, triggerActiveCount, deliveryConcernCount } = args;
  const reviewCount = Math.max(triggerReviewQueueCount, overviewState?.action_required_count ?? 0);
  const watchCount = Math.max(overviewState?.watch_count ?? 0, triggerActiveCount);

  if (reviewCount > 0 || deliveryConcernCount > 0) {
    return {
      state: "action_required" as const,
      headline: "Action required",
      interpretation: `${Math.max(reviewCount, 1)} ward${Math.max(reviewCount, 1) === 1 ? "" : "s"} awaiting review`,
      triggerActiveCount,
      deliveryConcernCount,
      reviewCount,
      showBanner: true,
    };
  }

  if (watchCount > 0) {
    return {
      state: "monitoring" as const,
      headline: "Monitoring triggers",
      interpretation: `${watchCount} ward${watchCount === 1 ? "" : "s"} under watch`,
      triggerActiveCount,
      deliveryConcernCount,
      reviewCount,
      showBanner: false,
    };
  }

  return {
    state: "stable" as const,
    headline: "No active triggers",
    interpretation: "System operating normally",
    triggerActiveCount,
    deliveryConcernCount,
    reviewCount,
    showBanner: false,
  };
}

function getFeatureAction(feature: WardMapFeature) {
  if (feature.properties.alert_count > 0) {
    return {
      why: `${feature.properties.alert_count} active alert${feature.properties.alert_count === 1 ? "" : "s"} require review in this ward.`,
      action: "Review ward alerts and investigate field conditions.",
    };
  }

  if (feature.properties.risk_level === "HIGH") {
    return {
      why: "This ward is currently classified as high risk in the latest visible model run.",
      action: "Open ward intelligence and review mitigation priorities.",
    };
  }

  if (feature.properties.risk_level === "MEDIUM") {
    return {
      why: "This ward is trending at watch level and may need closer review.",
      action: "Monitor closely and compare with adjacent wards.",
    };
  }

  return {
    why: "No immediate hotspot signal is visible for this ward right now.",
    action: "Continue routine monitoring.",
  };
}

function getMapFeatureRiskLevel(feature: WardMapFeature, riskMode: OverviewRiskMode) {
  return riskMode === "predicted" ? feature.properties.prediction.predicted_risk_level : feature.properties.current_risk_level;
}

function getMapFeatureRiskScore(feature: WardMapFeature, riskMode: OverviewRiskMode) {
  return riskMode === "predicted" ? feature.properties.prediction.predicted_risk_score : feature.properties.current_risk_score;
}

function getMapFeaturePredictedCases(feature: WardMapFeature, riskMode: OverviewRiskMode) {
  return riskMode === "predicted" ? feature.properties.prediction.predicted_cases : feature.properties.predicted_cases;
}

function formatDecisionModeLabel(mode: OverviewDecisionMode) {
  if (mode === "triggered") return "Triggered";
  if (mode === "alert_active") return "Alert Active";
  if (mode === "facility_capacity_concern") return "Capacity Concern";
  return "Risk Only";
}

function formatEligibleActionLabel(action: OverviewEligibleAction) {
  if (action === "view_alerts") return "Review alerts";
  if (action === "dispatch_chvs") return "Dispatch CHVs";
  if (action === "send_message") return "Send message";
  return "Investigate";
}

function getMapControlClass(isActive: boolean) {
  return isActive
    ? "border-brand bg-[color-mix(in_srgb,var(--brand)_14%,transparent)] text-panel-strong shadow-[0_10px_24px_rgba(29,111,218,0.12)]"
    : "border-panel-table-wrap bg-panel/70 text-panel-muted hover:border-brand/40 hover:text-panel-strong";
}

function getSecondaryTabClass(isActive: boolean) {
  return isActive
    ? "border-brand bg-brand text-white"
    : "border-panel-table-wrap bg-panel/70 text-panel-copy hover:border-brand/40 hover:text-panel-strong";
}

function getKpiCardClass(activeTone: "brand" | "danger" | "warning" | "alerts", isActive: boolean) {
  if (!isActive) {
    return "p-0";
  }

  if (activeTone === "danger") {
    return "overflow-hidden border-[color-mix(in_srgb,var(--danger)_34%,var(--dashboard-panel-border))] ring-1 ring-[color:var(--danger)]/20 p-0";
  }

  if (activeTone === "warning") {
    return "overflow-hidden border-[color-mix(in_srgb,var(--warning)_34%,var(--dashboard-panel-border))] ring-1 ring-[color:var(--warning)]/20 p-0";
  }

  if (activeTone === "alerts") {
    return "overflow-hidden border-[color-mix(in_srgb,#F97316_34%,var(--dashboard-panel-border))] ring-1 ring-[#F97316]/20 p-0";
  }

  return "overflow-hidden border-brand/35 ring-1 ring-brand/20 p-0";
}

function formatKpiDeltaLabel(delta: number, contextLabel: string, unitSuffix = "") {
  if (delta === 0) {
    return `No change ${contextLabel.replace("previous ", "")}`;
  }

  const absolute = Math.abs(delta);
  const signed = delta > 0 ? `+${absolute}` : `-${absolute}`;
  return `${signed}${unitSuffix} ${contextLabel}`;
}

function getKpiDeltaTone(delta: number, positiveIsGood: boolean) {
  if (delta > 0) {
    return positiveIsGood ? "text-[color:var(--success)]" : "text-[color:var(--danger)]";
  }
  if (delta < 0) {
    return positiveIsGood ? "text-[color:var(--danger)]" : "text-[color:var(--success)]";
  }
  return "text-panel-muted";
}

function KpiDelta({
  delta,
  contextLabel,
  unitSuffix = "",
  positiveIsGood = false,
}: {
  delta: number;
  contextLabel: string;
  unitSuffix?: string;
  positiveIsGood?: boolean;
}) {
  const Icon = delta > 0 ? TrendingUp : delta < 0 ? TrendingDown : ArrowRight;

  return (
    <p className={`inline-flex items-center gap-1 text-xs font-semibold ${getKpiDeltaTone(delta, positiveIsGood)}`}>
      <Icon className="size-3.5" aria-hidden="true" />
      <span>{formatKpiDeltaLabel(delta, contextLabel, unitSuffix)}</span>
    </p>
  );
}

function getGuidanceTone(label: string) {
  if (label.includes("triggered")) return "danger" as const;
  if (label.includes("alert")) return "warning" as const;
  return "info" as const;
}

function getFacilitySignalTone(state: "ready" | "watch" | "capacity_concern") {
  if (state === "capacity_concern") return "danger" as const;
  if (state === "watch") return "warning" as const;
  return "success" as const;
}

function formatFacilitySignalLabel(state: "ready" | "watch" | "capacity_concern") {
  if (state === "capacity_concern") return "Capacity concern";
  if (state === "watch") return "Under watch";
  return "Ready";
}

function getTriggerSeverityTone(severity: "high" | "medium" | "review") {
  if (severity === "high") return "danger" as const;
  if (severity === "medium") return "warning" as const;
  return "default" as const;
}

function formatTriggerSeverityLabel(severity: "high" | "medium" | "review") {
  if (severity === "high") return "High severity";
  if (severity === "medium") return "Watch severity";
  return "Review";
}

function getTriggerDeliveryTone(state: OverviewTriggeredWard["alert_delivery_state"]) {
  if (state === "triggered_failed") return "danger" as const;
  if (state === "triggered_retry_pending" || state === "triggered_queued") return "warning" as const;
  if (state === "triggered_delivered") return "success" as const;
  return "default" as const;
}

function getTriggerWorkflowTone(state: OverviewTriggeredWard["workflow_state"]) {
  if (state === "ACTION_IN_PROGRESS") return "danger" as const;
  if (state === "REVIEW_PENDING") return "warning" as const;
  if (state === "TRIGGER_ACTIVE" || state === "RESOLVED") return "success" as const;
  return "default" as const;
}

export default function OverviewPage() {
  const { currentUser } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const overviewQuery = useOverviewQuery({ enabled: Boolean(currentUser) });
  const overview = overviewQuery.data ?? null;
  const error = overviewQuery.error instanceof Error ? overviewQuery.error.message : null;
  const isLoading = overviewQuery.isPending;
  const isRefreshing = overviewQuery.isFetching;
  const [mapFilter, setMapFilter] = useState<OverviewMapFilter>("all");
  const [riskMode, setRiskMode] = useState<OverviewRiskMode>("current");
  const [hoveredMapFilter, setHoveredMapFilter] = useState<OverviewMapFilter | null>(null);
  const [selectedWardId, setSelectedWardId] = useState<number | null>(null);
  const [selectedTriggerId, setSelectedTriggerId] = useState<string | null>(null);
  const [simulationRun, setSimulationRun] = useState<ScenarioSimulationRun | null>(null);
  const [simulationPending, setSimulationPending] = useState<"RAINFALL_INCREASE" | "RESPONSE_DELAY" | null>(null);
  const [simulationError, setSimulationError] = useState<string | null>(null);
  const [simulationPreviewActive, setSimulationPreviewActive] = useState(false);
  const [activeGuidanceKey, setActiveGuidanceKey] = useState<
    "top_triggered_ward" | "most_active_alert_ward" | "biggest_recent_escalation" | "predicted_highest_risk_ward" | null
  >("top_triggered_ward");
  const [activeSidebarTab, setActiveSidebarTab] = useState<"action" | "triggers" | "readiness" | "scenarios">("action");
  const [recentAlertsFilter, setRecentAlertsFilter] = useState<RecentAlertFilter>("ALL");
  const [activeIssuesOnly, setActiveIssuesOnly] = useState(false);
  const actionFocusRef = useRef<HTMLDivElement | null>(null);

  const wardFeatures = useMemo(() => overview?.wardMap?.features ?? [], [overview?.wardMap?.features]);
  const selectedFeature = useMemo(
    () => wardFeatures.find((feature) => feature.properties.backend_ward_id === selectedWardId) ?? null,
    [selectedWardId, wardFeatures],
  );
  const hotspotHighlightWardId = selectedWardId ?? overview?.recentAlerts[0]?.ward ?? null;
  const topAlertWard = useMemo(
    () =>
      [...wardFeatures]
        .filter((feature) => feature.properties.alert_count > 0)
        .sort((left, right) => {
          if (right.properties.alert_count !== left.properties.alert_count) {
            return right.properties.alert_count - left.properties.alert_count;
          }

          const leftRisk = left.properties.risk_level === "HIGH" ? 3 : left.properties.risk_level === "MEDIUM" ? 2 : 1;
          const rightRisk = right.properties.risk_level === "HIGH" ? 3 : right.properties.risk_level === "MEDIUM" ? 2 : 1;
          return rightRisk - leftRisk;
        })[0] ?? null,
    [wardFeatures],
  );
  const topCurrentRiskWard = useMemo(
    () =>
      [...wardFeatures]
        .sort((left, right) => {
          const rightLevel = getMapFeatureRiskLevel(right, "current") === "HIGH" ? 3 : getMapFeatureRiskLevel(right, "current") === "MEDIUM" ? 2 : 1;
          const leftLevel = getMapFeatureRiskLevel(left, "current") === "HIGH" ? 3 : getMapFeatureRiskLevel(left, "current") === "MEDIUM" ? 2 : 1;
          if (rightLevel !== leftLevel) {
            return rightLevel - leftLevel;
          }
          return (getMapFeatureRiskScore(right, "current") ?? 0) - (getMapFeatureRiskScore(left, "current") ?? 0);
        })[0] ?? null,
    [wardFeatures],
  );
  const mapGuidance = overview?.mapGuidance ?? null;
  const triggerLinkage = overview?.triggerLinkage ?? null;
  const facilityReadiness = overview?.facilityReadiness ?? null;
  const simulationReadiness = overview?.simulationReadiness ?? null;
  const triggerReviewQueue = useMemo(
    () => overview?.triggerReviewQueue ?? [],
    [overview?.triggerReviewQueue],
  );
  const triggerSurfaceState = useMemo(
    () =>
      deriveTriggerSurfaceState({
        overviewState: overview?.overviewState,
        triggerReviewQueueCount: triggerReviewQueue.length,
        triggerActiveCount: overview?.triggerLinkage?.triggered_wards.length ?? 0,
        deliveryConcernCount: overview?.triggerLinkage?.delivery_concern_wards_count ?? 0,
      }),
    [
      overview?.overviewState,
      overview?.triggerLinkage?.delivery_concern_wards_count,
      overview?.triggerLinkage?.triggered_wards.length,
      triggerReviewQueue.length,
    ],
  );
  const activeGuidanceTarget = useMemo(() => {
    if (!mapGuidance || !activeGuidanceKey) {
      return null;
    }
    return mapGuidance[activeGuidanceKey] ?? null;
  }, [activeGuidanceKey, mapGuidance]);
  const activeWardFacilitySignal = useMemo(() => {
    const wardId = selectedWardId ?? activeGuidanceTarget?.ward_id ?? null;
    if (!facilityReadiness || !wardId) {
      return null;
    }
    return facilityReadiness.ward_capacity_signals.find((signal) => signal.ward_id === wardId) ?? null;
  }, [activeGuidanceTarget?.ward_id, facilityReadiness, selectedWardId]);

  useEffect(() => {
    if (!mapGuidance) {
      return;
    }
    if (riskMode === "predicted" && mapGuidance.predicted_highest_risk_ward) {
      setActiveGuidanceKey("predicted_highest_risk_ward");
      return;
    }
    if (mapGuidance.top_triggered_ward) {
      setActiveGuidanceKey("top_triggered_ward");
      return;
    }
    if (mapGuidance.biggest_recent_escalation) {
      setActiveGuidanceKey("biggest_recent_escalation");
    }
  }, [mapGuidance, riskMode]);

  async function handleRunSimulation(scenarioId: "RAINFALL_INCREASE" | "RESPONSE_DELAY") {
    setSimulationPending(scenarioId);
    setSimulationError(null);
    setSimulationPreviewActive(false);
    try {
      const result = await runScenarioSimulationViaBff(
        scenarioId === "RAINFALL_INCREASE"
          ? { scenario_id: scenarioId, rainfall_uplift_percent: 20 }
          : { scenario_id: scenarioId, response_delay_hours: 12 },
      );
      setSimulationRun(result);
    } catch (error) {
      setSimulationError(error instanceof Error ? error.message : "Unable to run scenario simulation.");
    } finally {
      setSimulationPending(null);
    }
  }

  function handleJumpToActionFocus() {
    setActiveSidebarTab("action");

    requestAnimationFrame(() => {
      actionFocusRef.current?.scrollIntoView({
        behavior: "smooth",
        block: "start",
      });
    });
  }

  function handlePreviewSimulationOnMap() {
    if (!simulationRun?.ward_results.length) {
      return;
    }

    const previewResult = scopedScenarioWardResult ?? simulationRun.ward_results[0];
    setSimulationPreviewActive(true);
    setRiskMode("predicted");
    if (wardFeatures.some((feature) => feature.properties.backend_ward_id === previewResult.ward_id)) {
      setSelectedWardId(previewResult.ward_id);
    }
    setActiveSidebarTab("action");

    requestAnimationFrame(() => {
      window.scrollTo({
        top: 0,
        behavior: "smooth",
      });
    });
  }

  const selectedActionSummary = useMemo(() => {
    if (!selectedFeature) {
      return null;
    }

    const action = getFeatureAction(selectedFeature);
    return {
      wardName: selectedFeature.properties.name,
      riskLevel: getMapFeatureRiskLevel(selectedFeature, riskMode),
      riskScore: getMapFeatureRiskScore(selectedFeature, riskMode),
      predictedCases: getMapFeaturePredictedCases(selectedFeature, riskMode),
      alertCount: selectedFeature.properties.alert_count,
      reason:
        riskMode === "predicted"
          ? `Predicted 7-day outlook: ${action.why}`
          : action.why,
      recommendedAction:
        riskMode === "predicted"
          ? `Prediction review: ${action.action}`
          : action.action,
      decisionMode: selectedFeature.properties.alert_count > 0 ? ("triggered" as const) : ("risk_only" as const),
      eligibleActions: selectedFeature.properties.alert_count > 0
        ? (["view_alerts", "investigate", "dispatch_chvs"] as const)
        : (["investigate", "view_alerts"] as const),
      wardId: selectedFeature.properties.backend_ward_id,
    };
  }, [riskMode, selectedFeature]);
  const panelContext = useMemo(() => {
    if (selectedActionSummary) {
      return {
        title: "Action Focus",
        subtitle:
          riskMode === "predicted"
            ? "Selected hotspot context overrides the default predicted priority queue."
            : "Selected hotspot context overrides the default priority queue.",
        ...selectedActionSummary,
        sourceLabel: riskMode === "predicted" ? "Predicted map selection" : "Map selection",
      };
    }

    if (riskMode === "predicted" && overview?.decisionSummary.top_priority_ward) {
      const top = overview.decisionSummary.top_priority_ward;
      return {
        title: "Action Focus",
        subtitle: "Predicted 7-day backend priority ward in the visible dashboard scope.",
        wardName: top.ward_name,
        riskLevel: top.risk_level,
        riskScore: top.risk_score,
        predictedCases: top.predicted_cases,
        alertCount: top.alert_count,
        reason: `Predicted 7-day outlook: ${overview.decisionSummary.reason_flagged}`,
        recommendedAction: `Prediction review: ${overview.decisionSummary.recommended_action}`,
        decisionMode: overview.decisionSummary.decision_mode,
        eligibleActions: overview.decisionSummary.eligible_actions,
        wardId: top.ward_id,
        sourceLabel: "Predicted backend priority",
      };
    }

    const filterSummary =
      mapFilter === "alerts"
        ? "Alert-focused view is active. Review recent visible alerts and confirm if any ward needs escalation."
        : mapFilter === "workflow_active"
          ? "Workflow-active wards are in focus. Review backend trigger reasoning before duplicating response work."
          : mapFilter === "delivery_concern"
            ? "Delivery concern view is active. Prioritize wards with failed or retry-pending alert delivery."
        : mapFilter === "medium"
          ? "Watch-level map focus is active. Compare medium-risk wards before escalating."
          : mapFilter === "high"
            ? "High-risk map focus is active, but no promoted priority ward is currently available."
            : "No priority ward is currently nominated by the backend.";

    const fallbackWardName = overview?.decisionSummary.top_priority_ward?.ward_name ?? null;
    const fallbackRiskLevel = overview?.decisionSummary.top_priority_ward?.risk_level ?? null;
    const fallbackRiskScore = overview?.decisionSummary.top_priority_ward?.risk_score ?? null;
    const fallbackPredictedCases = overview?.decisionSummary.top_priority_ward?.predicted_cases ?? 0;
    const fallbackAlertCount = overview?.decisionSummary.top_priority_ward?.alert_count ?? 0;
    const fallbackWardId = overview?.decisionSummary.top_priority_ward?.ward_id ?? null;

    return {
      title: "Action Focus",
      subtitle:
        riskMode === "predicted"
          ? "Predicted 7-day overview"
          : triggerSurfaceState.state === "action_required"
            ? "Highest-priority ward awaiting trigger review."
            : triggerSurfaceState.state === "monitoring"
              ? "Monitoring visible ward conditions."
              : "System stable",
      wardName: (riskMode === "predicted" ? topAlertWard : topCurrentRiskWard)?.properties.name ?? fallbackWardName,
      riskLevel: (riskMode === "predicted" ? topAlertWard : topCurrentRiskWard)
        ? getMapFeatureRiskLevel((riskMode === "predicted" ? topAlertWard : topCurrentRiskWard) as WardMapFeature, riskMode)
        : fallbackRiskLevel,
      riskScore: (riskMode === "predicted" ? topAlertWard : topCurrentRiskWard)
        ? getMapFeatureRiskScore((riskMode === "predicted" ? topAlertWard : topCurrentRiskWard) as WardMapFeature, riskMode)
        : fallbackRiskScore,
      predictedCases: (riskMode === "predicted" ? topAlertWard : topCurrentRiskWard)
        ? getMapFeaturePredictedCases((riskMode === "predicted" ? topAlertWard : topCurrentRiskWard) as WardMapFeature, riskMode)
        : fallbackPredictedCases,
      alertCount: (riskMode === "predicted" ? topAlertWard : topCurrentRiskWard)?.properties.alert_count ?? fallbackAlertCount,
      reason:
        riskMode === "predicted"
          ? overview?.decisionSummary.reason_flagged
            ? `Predicted 7-day outlook: ${overview.decisionSummary.reason_flagged}`
            : filterSummary
          : filterSummary,
      recommendedAction:
        riskMode === "predicted"
          ? overview?.decisionSummary.recommended_action
            ? `Prediction review: ${overview.decisionSummary.recommended_action}`
            : "Review the predicted 7-day outlook and compare it with current field conditions."
          : "Continue routine monitoring.",
      decisionMode: riskMode === "predicted" ? (overview?.decisionSummary.decision_mode ?? "risk_only") : "risk_only",
      eligibleActions:
        riskMode === "predicted"
          ? (overview?.decisionSummary.eligible_actions ?? (["investigate", "view_alerts"] as const))
          : (["investigate", "view_alerts"] as const),
      wardId: (riskMode === "predicted" ? topAlertWard : topCurrentRiskWard)?.properties.backend_ward_id ?? fallbackWardId,
      sourceLabel: riskMode === "predicted" ? "Predicted outlook" : mapFilter === "all" ? "Current baseline" : `${getMapFilterLabel(mapFilter)} filter`,
    };
  }, [mapFilter, overview, riskMode, selectedActionSummary, topAlertWard, topCurrentRiskWard, triggerSurfaceState.state]);
  const recentAlertsRows = useMemo(() => {
    const alerts = overview?.recentAlerts ?? [];
    const scopedAlerts = alerts.filter((alert) => {
      const riskLevel = deriveAlertRiskLevel(alert.risk_score);

      if (activeIssuesOnly && !["RETRY_PENDING", "FAILED"].includes(alert.status)) {
        return false;
      }

      if (recentAlertsFilter === "RETRY_PENDING") {
        return alert.status === "RETRY_PENDING";
      }

      if (recentAlertsFilter === "DELIVERED") {
        return alert.status === "DELIVERED";
      }

      if (recentAlertsFilter === "HIGH_RISK") {
        return riskLevel === "HIGH";
      }

      return true;
    });

    return [...scopedAlerts].sort((left, right) => {
      const statusDiff = getOperationalAlertStatusRank(left.status) - getOperationalAlertStatusRank(right.status);
      if (statusDiff !== 0) {
        return statusDiff;
      }

      return new Date(right.created_at).getTime() - new Date(left.created_at).getTime();
    });
  }, [activeIssuesOnly, overview?.recentAlerts, recentAlertsFilter]);
  const recentAlertWardCounts = useMemo(() => {
    return recentAlertsRows.reduce<Record<string, number>>((accumulator, alert) => {
      accumulator[alert.ward_name] = (accumulator[alert.ward_name] ?? 0) + 1;
      return accumulator;
    }, {});
  }, [recentAlertsRows]);
  const allVisibleAlertsAreStale = useMemo(() => {
    return recentAlertsRows.length > 0 && recentAlertsRows.every((alert) => isOperationallyStaleAlert(alert.created_at));
  }, [recentAlertsRows]);
  const activeTriggeredWard = useMemo(() => {
    const wardId = selectedWardId ?? activeGuidanceTarget?.ward_id ?? panelContext.wardId ?? null;
    if (!triggerLinkage || !wardId) {
      return null;
    }
    return triggerLinkage.triggered_wards.find((item) => item.ward_id === wardId) ?? null;
  }, [activeGuidanceTarget?.ward_id, panelContext.wardId, selectedWardId, triggerLinkage]);
  const topScenarioWardResult = simulationRun?.ward_results[0] ?? null;
  const scopedScenarioWardResult = useMemo(() => {
    if (!simulationRun?.ward_results.length || !wardFeatures.length) {
      return null;
    }

    const visibleWardIds = new Set(
      wardFeatures
        .map((feature) => feature.properties.backend_ward_id)
        .filter((wardId): wardId is number => typeof wardId === "number"),
    );
    const visibleWardNames = new Set(wardFeatures.map((feature) => normalizeWardKey(feature.properties.name)));

    return (
      simulationRun.ward_results.find(
        (result) => visibleWardIds.has(result.ward_id) || visibleWardNames.has(normalizeWardKey(result.ward_name)),
      ) ?? null
    );
  }, [simulationRun?.ward_results, wardFeatures]);
  const activeTrigger = useMemo(
    () => triggerReviewQueue.find((item) => item.trigger_id === selectedTriggerId) ?? null,
    [selectedTriggerId, triggerReviewQueue],
  );
  const createAlertFixedWard = useMemo(() => {
    if (!selectedFeature?.properties.backend_ward_id) {
      return null;
    }

    return {
      id: selectedFeature.properties.backend_ward_id,
      name: selectedFeature.properties.name,
      county: null,
      subCounty: null,
      riskLevel: (selectedFeature.properties.current_risk_level ?? "UNKNOWN") as "LOW" | "MEDIUM" | "HIGH" | "UNKNOWN",
      riskScore: selectedFeature.properties.current_risk_score ?? null,
      predictedCases: selectedFeature.properties.prediction?.predicted_cases ?? null,
      updatedAt: selectedFeature.properties.risk_generated_at ?? null,
    };
  }, [selectedFeature]);

  useEffect(() => {
    const requestedWardId = searchParams.get("trigger_review");
    if (!requestedWardId || !triggerReviewQueue.length) {
      return;
    }

    const requestedTrigger =
      triggerReviewQueue.find((item) => item.trigger_id === requestedWardId) ??
      triggerReviewQueue.find((item) => String(item.ward_id) === requestedWardId);

    if (requestedTrigger) {
      setSelectedTriggerId(requestedTrigger.trigger_id);
    }
  }, [searchParams, triggerReviewQueue]);

  if (!currentUser) {
    return null;
  }

  const priorityWardPanel = overview?.decisionSummary.top_priority_ward ? (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-[1rem] border border-panel-table-wrap bg-panel/55 px-4 py-3">
      <div className="min-w-0 space-y-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[10px] font-semibold uppercase tracking-[0.18em] text-panel-muted">
            {riskMode === "predicted" ? "Predicted priority ward" : "Priority ward"}
          </span>
          <span className="text-sm font-semibold text-panel-strong">
            {overview.decisionSummary.top_priority_ward.ward_name}
          </span>
        </div>
        <p className="text-sm text-panel-copy">
          {riskMode === "predicted"
            ? `Predicted 7-day outlook: ${overview.decisionSummary.reason_flagged}`
            : overview.decisionSummary.reason_flagged}
        </p>
      </div>
      <div className="flex items-center gap-3">
        <p className="hidden text-xs font-medium text-brand md:block">
          Next: {overview.decisionSummary.recommended_action}
        </p>
        <button
          type="button"
          className="inline-flex h-9 items-center justify-center rounded-pill border border-brand bg-[color-mix(in_srgb,var(--brand)_10%,white)] px-4 text-sm font-semibold text-brand transition hover:bg-[color-mix(in_srgb,var(--brand)_16%,white)]"
          onClick={() => setSelectedWardId(overview.decisionSummary.top_priority_ward?.ward_id ?? null)}
        >
          Focus ward
        </button>
      </div>
    </div>
  ) : null;

  return (
    <div className="space-y-6">
      <DashboardTopbar
        title="Early Warning & Action"
        subtitle="Predict risk, trigger action, and coordinate response"
        onRefresh={() => {
          void overviewQuery.refetch();
        }}
      >
        <TriggerAlertPanel
          buttonLabel="Create Alert"
          closeLabel="Close Alert Flow"
          buttonClassName="inline-flex h-11 items-center justify-center gap-2 rounded-[0.8rem] bg-[linear-gradient(180deg,#1d6fda_0%,#175fc2_100%)] px-4 text-sm font-semibold text-white shadow-[0_16px_32px_rgba(23,95,194,0.22)] transition hover:-translate-y-px"
          fixedWard={createAlertFixedWard}
        />
      </DashboardTopbar>
      <TriggerReviewDrawer trigger={activeTrigger} onClose={() => setSelectedTriggerId(null)} />

      {error ? (
        <div className="rounded-2xl border border-[color-mix(in_srgb,var(--danger)_20%,white)] bg-[color-mix(in_srgb,var(--danger)_10%,white)] px-4 py-3 text-sm font-medium text-[color:var(--danger)] dark:border-[color-mix(in_srgb,var(--danger)_34%,transparent)] dark:bg-[color-mix(in_srgb,var(--danger)_18%,transparent)]">
          <AlertTriangle className="mr-2 inline-flex size-4" aria-hidden="true" />
          {error}
        </div>
      ) : null}

      <section className="grid gap-4 xl:grid-cols-4">
        <Card className="p-0">
          <button
            type="button"
            title="Show latest trigger lead time"
            className="flex h-[122px] w-full items-start gap-3 rounded-panel p-4 text-left transition"
            onClick={() => setActiveSidebarTab("triggers")}
            onMouseEnter={() => setHoveredMapFilter(null)}
            onMouseLeave={() => setHoveredMapFilter(null)}
          >
            <div className="inline-flex size-10 shrink-0 items-center justify-center rounded-2xl bg-[color-mix(in_srgb,var(--dashboard-sidebar-title)_18%,var(--dashboard-panel-surface))] text-brand">
              <Activity className="size-4.5" aria-hidden="true" />
            </div>
            <div className="space-y-1.5">
              <span className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted">Last trigger lead time</span>
              <strong className="block text-3xl font-semibold tracking-[-0.05em] text-panel-strong">
                {isLoading
                  ? "..."
                  : overview?.missionMetrics.last_trigger_lead_time_hours != null
                    ? overview.missionMetrics.last_trigger_lead_time_label
                    : "—"}
              </strong>
              <p className="text-xs text-panel-muted">
                {overview?.missionMetrics.last_triggered_at
                  ? `Last trigger ${formatCompactRelativeMinutes(overview.missionMetrics.last_triggered_at)}`
                  : "Awaiting trigger evidence"}
              </p>
            </div>
          </button>
        </Card>

        <Card className={getKpiCardClass("danger", mapFilter === "high")}>
          <button
            type="button"
            title="Filter map to high-risk wards"
            className="flex h-[122px] w-full items-start gap-3 rounded-panel p-4 text-left transition"
            onClick={() => setMapFilter((current) => (current === "high" ? "all" : "high"))}
            onMouseEnter={() => setHoveredMapFilter("high")}
            onMouseLeave={() => setHoveredMapFilter(null)}
          >
            <div className="inline-flex size-10 shrink-0 items-center justify-center rounded-2xl bg-[color-mix(in_srgb,var(--danger)_18%,var(--dashboard-panel-surface))] text-[color:var(--danger)]">
              <TriangleAlert className="size-4.5" aria-hidden="true" />
            </div>
            <div className="space-y-1.5">
              <StatusBadge tone="danger" className="rounded-full px-3 py-1 tracking-[0.14em]">
                High risk wards
              </StatusBadge>
              <strong className="block text-3xl font-semibold tracking-[-0.05em] text-panel-strong">
                {isLoading ? "..." : overview?.highRiskWards.length ?? 0}
              </strong>
              {!isLoading && overview ? (
                <KpiDelta
                  delta={overview.temporalMetrics.high_risk.delta}
                  contextLabel={overview.temporalMetrics.high_risk.context_label}
                />
              ) : null}
            </div>
          </button>
        </Card>

        <Card className={getKpiCardClass("warning", mapFilter === "workflow_active")}>
          <button
            type="button"
            title="Filter map to workflow-active wards"
            className="flex h-[122px] w-full items-start gap-3 rounded-panel p-4 text-left transition"
            onClick={() => {
              setMapFilter((current) => (current === "workflow_active" ? "all" : "workflow_active"));
              setActiveSidebarTab("triggers");
            }}
            onMouseEnter={() => setHoveredMapFilter("workflow_active")}
            onMouseLeave={() => setHoveredMapFilter(null)}
          >
            <div className="inline-flex size-10 shrink-0 items-center justify-center rounded-2xl bg-[color-mix(in_srgb,var(--warning)_18%,var(--dashboard-panel-surface))] text-[color:var(--warning)]">
              <CircleAlert className="size-4.5" aria-hidden="true" />
            </div>
            <div className="space-y-1.5">
              <StatusBadge tone="warning" className="rounded-full px-3 py-1 tracking-[0.14em]">
                Workflow-active wards
              </StatusBadge>
              <strong className="block text-3xl font-semibold tracking-[-0.05em] text-panel-strong">
                {isLoading ? "..." : overview?.missionMetrics.workflow_active_wards_count ?? 0}
              </strong>
              <p className="text-xs text-panel-muted">
                {overview?.missionMetrics.workflow_active_wards_count
                  ? `${overview.missionMetrics.trigger_delivery_concern_count} delivery concern${overview.missionMetrics.trigger_delivery_concern_count === 1 ? "" : "s"}`
                  : "No live workflow queue"}
              </p>
            </div>
          </button>
        </Card>

        <Card className={getKpiCardClass("alerts", mapFilter === "alerts")}>
          <button
            type="button"
            title="Filter map to active alerts"
            className="flex h-[122px] w-full items-start gap-3 rounded-panel p-4 text-left transition"
            onClick={() => setMapFilter((current) => (current === "alerts" ? "all" : "alerts"))}
            onMouseEnter={() => setHoveredMapFilter("alerts")}
            onMouseLeave={() => setHoveredMapFilter(null)}
          >
            <div className="inline-flex size-10 shrink-0 items-center justify-center rounded-2xl bg-[color-mix(in_srgb,var(--dashboard-table-line)_72%,var(--dashboard-panel-surface))] text-panel-copy">
              <Bell className="size-4.5" aria-hidden="true" />
            </div>
            <div className="space-y-1.5">
              <StatusBadge tone="default" className="rounded-full px-3 py-1 tracking-[0.14em]">
                Active alerts
              </StatusBadge>
              <strong className="block text-3xl font-semibold tracking-[-0.05em] text-panel-strong">
                {isLoading ? "..." : overview?.alertsTodayCount ?? 0}
              </strong>
              {!isLoading && overview ? (
                overview.temporalMetrics.alerts_today.delta !== 0 ? (
                  <KpiDelta
                    delta={overview.temporalMetrics.alerts_today.delta}
                    contextLabel={overview.temporalMetrics.alerts_today.context_label}
                  />
                ) : (
                  <p className="text-xs text-panel-muted">
                    {overview.deliveredAlertRate}% delivered
                  </p>
                )
              ) : null}
            </div>
          </button>
        </Card>
      </section>

      {triggerSurfaceState.showBanner ? (
        <Card className="p-3">
          <div
            className={`rounded-[1.35rem] border px-4 py-3 ${getSystemStateSurfaceClass(
              overview?.overviewState.system_state ?? "stable",
            )}`}
          >
            <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
              <div className="space-y-1">
                <div className="flex items-center gap-2.5">
                  <StatusBadge tone="danger" className="rounded-full px-3 py-1 tracking-[0.14em]">
                    Action required
                  </StatusBadge>
                  <span className="text-sm font-medium text-panel-strong">{triggerSurfaceState.interpretation}</span>
                </div>
                <p className="text-sm text-panel-copy">
                  {triggerSurfaceState.reviewCount} ward{triggerSurfaceState.reviewCount === 1 ? "" : "s"} awaiting review •{" "}
                  {triggerSurfaceState.deliveryConcernCount} delivery issue{triggerSurfaceState.deliveryConcernCount === 1 ? "" : "s"}
                </p>
              </div>

              <button
                type="button"
                className="inline-flex h-10 items-center justify-center rounded-pill border border-brand bg-brand px-4 text-sm font-semibold text-white transition hover:brightness-[1.03]"
                onClick={handleJumpToActionFocus}
              >
                Review trigger queue
              </button>
            </div>
          </div>
        </Card>
      ) : null}

      <section className="grid gap-6 xl:grid-cols-[minmax(0,1.7fr)_minmax(320px,0.9fr)]">
        <Card className="space-y-3 p-5">
          <PageSectionHeader
            title="Priority Wards for Action"
            description={
              riskMode === "predicted"
                ? "Predicted 7-day ward risk"
                : "Current ward risk and alert activity"
            }
          />
          {simulationPreviewActive && simulationRun && (scopedScenarioWardResult ?? topScenarioWardResult) ? (
            <div className="rounded-[1.2rem] border border-[color-mix(in_srgb,var(--brand)_24%,white)] bg-[color-mix(in_srgb,var(--brand)_8%,white)] px-4 py-3 text-sm text-panel-copy dark:border-[color-mix(in_srgb,var(--brand)_28%,transparent)] dark:bg-[color-mix(in_srgb,var(--brand)_12%,transparent)]">
              <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                <div className="space-y-1">
                  <p className="text-xs font-semibold uppercase tracking-[0.14em] text-brand">Simulation preview</p>
                  <p className="font-semibold text-panel-strong">Live outputs unchanged</p>
                  <p>
                    {simulationRun.summary.scenario_label} preview focused on {(scopedScenarioWardResult ?? topScenarioWardResult)?.ward_name} •{" "}
                    {formatScenarioRiskDelta(
                      (scopedScenarioWardResult ?? topScenarioWardResult)!.baseline_risk_score,
                      (scopedScenarioWardResult ?? topScenarioWardResult)!.simulated_risk_score,
                    )} •{" "}
                    {formatScenarioCaseDelta(
                      (scopedScenarioWardResult ?? topScenarioWardResult)!.baseline_predicted_cases,
                      (scopedScenarioWardResult ?? topScenarioWardResult)!.simulated_predicted_cases,
                    )}
                  </p>
                  {scopedScenarioWardResult && topScenarioWardResult && scopedScenarioWardResult.ward_id !== topScenarioWardResult.ward_id ? (
                    <p className="text-xs text-panel-muted">
                      Preview is anchored to the highest-impact ward visible in this dashboard scope.
                    </p>
                  ) : null}
                </div>
                <button
                  type="button"
                  className="inline-flex h-9 items-center justify-center rounded-pill border border-panel-table-wrap bg-panel/70 px-3 text-sm font-semibold text-panel-copy transition hover:border-brand/40 hover:text-panel-strong"
                  onClick={() => setSimulationPreviewActive(false)}
                >
                  Return to live view
                </button>
              </div>
            </div>
          ) : null}
          <div className="flex flex-wrap items-center gap-2">
            {([
              { key: "current", label: "Current" },
              { key: "predicted", label: "Predicted (7d)" },
            ] as const).map((item) => (
              <button
                key={item.key}
                type="button"
                className={`inline-flex h-8 items-center justify-center rounded-pill border px-3 text-sm font-semibold transition ${
                  riskMode === item.key
                    ? "border-brand bg-brand text-white"
                    : "border-panel-table-wrap bg-panel/70 text-panel-copy hover:border-brand/40 hover:text-panel-strong"
                }`}
                onClick={() => setRiskMode(item.key)}
              >
                {item.label}
              </button>
            ))}
          </div>
          {mapGuidance && activeGuidanceTarget ? (
            <details className="rounded-[1.1rem] border border-panel-table-wrap bg-panel/50 px-4 py-3">
              <summary className="cursor-pointer list-none text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted">
                Map guidance
              </summary>
              <div className="mt-3 flex flex-col gap-3">
                <div className="flex flex-wrap items-center gap-2">
                {([
                  ["top_triggered_ward", mapGuidance.top_triggered_ward],
                  ["most_active_alert_ward", mapGuidance.most_active_alert_ward],
                  ["biggest_recent_escalation", mapGuidance.biggest_recent_escalation],
                  ["predicted_highest_risk_ward", mapGuidance.predicted_highest_risk_ward],
                ] as const)
                  .filter(([, target]) => Boolean(target))
                  .map(([key, target]) => (
                    <button
                      key={key}
                      type="button"
                      className={`inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-semibold transition ${
                        activeGuidanceKey === key
                          ? "border-brand bg-brand text-white"
                          : "border-panel-table-wrap bg-panel/70 text-panel-copy hover:border-brand/40 hover:text-panel-strong"
                      }`}
                      onClick={() => {
                        setActiveGuidanceKey(key);
                        if (target) {
                          setSelectedWardId(target.ward_id);
                        }
                      }}
                    >
                      {target?.label}
                    </button>
                  ))}
                </div>
                {activeGuidanceTarget ? (
                  <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                    <div className="space-y-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <StatusBadge tone={getGuidanceTone(activeGuidanceTarget.label)} className="rounded-full px-3 py-1 tracking-[0.14em]">
                          {activeGuidanceTarget.label}
                        </StatusBadge>
                        <span className="text-sm font-semibold text-panel-strong">{activeGuidanceTarget.ward_name}</span>
                      </div>
                      <p className="text-sm text-panel-copy">{activeGuidanceTarget.reason}</p>
                    </div>
                    <button
                      type="button"
                      className="inline-flex h-10 items-center justify-center rounded-pill border border-brand bg-[color-mix(in_srgb,var(--brand)_10%,white)] px-4 text-sm font-semibold text-brand transition hover:bg-[color-mix(in_srgb,var(--brand)_16%,white)]"
                      onClick={() => setSelectedWardId(activeGuidanceTarget.ward_id)}
                    >
                      Focus ward
                    </button>
                  </div>
                ) : null}
              </div>
            </details>
          ) : null}
          <div className="flex flex-wrap items-center gap-2 text-xs font-semibold uppercase tracking-[0.12em] text-panel-muted">
            {([
              { key: "all", label: "All wards", dot: "bg-panel-copy" },
              { key: "high", label: "High risk", dot: "bg-[#DC2626]" },
              { key: "medium", label: "Medium risk", dot: "bg-[#F59E0B]" },
              { key: "low", label: "Low risk", dot: "bg-[#16A34A]" },
              { key: "alerts", label: "Active alerts", dot: "bg-[#F97316]" },
              { key: "workflow_active", label: "Workflow-active wards", dot: "bg-[#2563EB]" },
              { key: "delivery_concern", label: "Delivery concern", dot: "bg-[#C2410C]" },
            ] as const).map((item) => {
              const active = mapFilter === item.key;
              const hovered = hoveredMapFilter === item.key;

              return (
                <button
                  key={item.key}
                  type="button"
                  className={`inline-flex h-8 items-center gap-2 rounded-full border px-3 py-0 transition ${getMapControlClass(active || hovered)}`}
                  onClick={() => setMapFilter((current) => (current === item.key ? "all" : item.key))}
                  onMouseEnter={() => setHoveredMapFilter(item.key)}
                  onMouseLeave={() => setHoveredMapFilter(null)}
                >
                  <span className={`size-2.5 rounded-full ${item.dot}`} />
                  {item.label}
                </button>
              );
            })}
          </div>
          <div className="overflow-visible rounded-[1.75rem] border border-panel-table-wrap bg-[radial-gradient(circle_at_top_left,color-mix(in_srgb,var(--brand)_10%,transparent),transparent_38%),linear-gradient(135deg,color-mix(in_srgb,var(--panel)_94%,var(--background-fade)),var(--panel))] p-1">
          <div className="h-[31rem] lg:h-[33rem]">
            {overview?.wardMap?.features?.length ? (
              <OverviewHotspotMap
                features={overview.wardMap.features}
                highlightedWardId={hotspotHighlightWardId}
                focusedWardId={selectedWardId ?? activeGuidanceTarget?.ward_id ?? null}
                readinessSignals={overview.facilityReadiness.ward_capacity_signals}
                triggerLinkage={overview.triggerLinkage.triggered_wards}
                activeFilter={mapFilter}
                hoveredFilter={hoveredMapFilter}
                riskMode={riskMode}
                lastUpdatedLabel={formatCompactRelativeMinutes(overview?.latestTimestamp ?? null)}
                onSelectWard={(feature) => {
                  setSelectedWardId(feature.properties.backend_ward_id ?? null);
                }}
              />
            ) : (
              <div className="flex h-full items-center justify-center rounded-[1.35rem] border border-dashed border-panel-table-wrap px-6 text-center text-sm text-panel-muted">
                Hotspot geography is not available for this scope yet.
              </div>
            )}
          </div>
          </div>

          <div className="rounded-[1.2rem] border border-panel-table-wrap bg-panel/60 px-4 py-3 text-sm">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="text-panel-muted/80">
                Map mode: {riskMode === "predicted" ? "Predicted (7d)" : "Current"} • Focus: {getMapFilterLabel(mapFilter)}
              </span>
              <span className="font-medium text-panel-strong">
                {selectedFeature
                  ? `Selected ward: ${selectedFeature.properties.name}`
                  : activeGuidanceTarget
                    ? `Focused ward: ${activeGuidanceTarget.ward_name}`
                    : "Select a ward for details."}
              </span>
            </div>
          </div>
        </Card>

        <aside ref={actionFocusRef} className="space-y-4">
          <Card className="space-y-4 p-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <PageSectionHeader title={panelContext.title} description={panelContext.subtitle} />
              <div className="flex flex-wrap gap-2" role="tablist" aria-label="Overview side panels">
                {([
                  ["action", "Action"],
                  ["triggers", "Triggers"],
                  ["readiness", "Readiness"],
                  ["scenarios", "Scenarios"],
                ] as const).map(([key, label]) => (
                  <button
                    key={key}
                    type="button"
                    role="tab"
                    aria-selected={activeSidebarTab === key}
                    className={`inline-flex h-9 items-center justify-center rounded-pill border px-3 text-sm font-semibold transition ${getSecondaryTabClass(activeSidebarTab === key)}`}
                    onClick={() => setActiveSidebarTab(key)}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>

            {activeSidebarTab === "action" ? (
              <div className="space-y-4">
                {isLoading ? (
                  <Card className="rounded-[1.5rem] p-4 shadow-none">
                    <p className="text-sm text-panel-muted">Loading priority wards...</p>
                  </Card>
                ) : panelContext.wardName ? (
                  <>
                    <Card className={getAttentionCardClass(panelContext.riskLevel, true)}>
                      <div className="flex items-start justify-between gap-3">
                        <div className="space-y-1">
                          <strong className="text-lg font-semibold text-panel-strong">{panelContext.wardName}</strong>
                          <p className="text-sm text-panel-muted">{panelContext.sourceLabel}</p>
                        </div>
                        <StatusBadge
                          tone={getRiskBadgeTone(panelContext.riskLevel)}
                          className="rounded-full px-3 py-1 tracking-[0.14em]"
                        >
                          {panelContext.riskLevel ?? "Unknown"}
                        </StatusBadge>
                      </div>

                      <div className="grid grid-cols-2 gap-3 rounded-[1.2rem] border border-panel-table-wrap/80 bg-panel/60 p-4">
                        <div>
                          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-panel-muted">Alerts</p>
                          <strong className="mt-1 block text-2xl font-semibold text-panel-strong">{panelContext.alertCount}</strong>
                        </div>
                        <div>
                          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-panel-muted">
                            {riskMode === "predicted" ? "Predicted cases" : "Expected cases"}
                          </p>
                          <strong className="mt-1 block text-2xl font-semibold text-panel-strong">{panelContext.predictedCases}</strong>
                        </div>
                      </div>

                      <div>
                        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-panel-muted">Why it matters</p>
                        <p className="mt-1 line-clamp-2 text-sm text-panel-copy">{panelContext.reason}</p>
                      </div>
                      <div>
                        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-panel-muted">Recommended action</p>
                        <p className="mt-1 line-clamp-2 text-sm text-panel-copy">{panelContext.recommendedAction}</p>
                      </div>

                      {activeTriggeredWard ? (
                        <div className="rounded-[1.2rem] border border-panel-table-wrap/80 bg-panel/60 p-4">
                          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-panel-muted">Trigger status</p>
                          <div className="mt-2 flex items-center justify-between gap-3">
                            <p className="text-sm font-semibold text-panel-strong">{activeTriggeredWard.workflow_state_label}</p>
                            <StatusBadge
                              tone={getTriggerWorkflowTone(activeTriggeredWard.workflow_state)}
                              className="rounded-full px-3 py-1 tracking-[0.14em]"
                            >
                              {activeTriggeredWard.alert_count} alerts
                            </StatusBadge>
                          </div>
                          <p className="mt-2 text-xs text-panel-muted">Delivery status: {activeTriggeredWard.alert_delivery_label}</p>
                        </div>
                      ) : null}

                      {activeWardFacilitySignal ? (
                        <div className="rounded-[1.2rem] border border-panel-table-wrap/80 bg-panel/60 p-4">
                          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-panel-muted">Facility capacity</p>
                          <div className="mt-2 flex items-center justify-between gap-3">
                            <p className="text-sm font-semibold text-panel-strong">
                              {formatFacilitySignalLabel(activeWardFacilitySignal.facility_capacity_signal)}
                            </p>
                            <StatusBadge
                              tone={getFacilitySignalTone(activeWardFacilitySignal.facility_capacity_signal)}
                              className="rounded-full px-3 py-1 tracking-[0.14em]"
                            >
                              {activeWardFacilitySignal.facility_count} facilities
                            </StatusBadge>
                          </div>
                        </div>
                      ) : null}

                      <div className="flex flex-wrap gap-3 pt-1">
                        {panelContext.wardId ? (
                          <button
                            type="button"
                            className="inline-flex items-center gap-2 rounded-full bg-[linear-gradient(180deg,#1d6fda_0%,#175fc2_100%)] px-4 py-2 text-sm font-semibold text-white shadow-[0_12px_24px_rgba(23,95,194,0.18)] transition hover:-translate-y-px"
                            onClick={() => router.push(`/wards/${panelContext.wardId}`)}
                          >
                            View ward
                            <ArrowRight className="size-4" aria-hidden="true" />
                          </button>
                        ) : null}
                        <Link
                          href="/alerts"
                          className="inline-flex items-center gap-2 rounded-full border border-panel-table-wrap px-4 py-2 text-sm font-semibold text-panel-strong transition hover:border-brand/40 hover:text-brand"
                        >
                          Review alerts
                        </Link>
                        {triggerReviewQueue.length ? (
                          <button
                            type="button"
                            className="inline-flex items-center gap-2 rounded-full border border-panel-table-wrap bg-transparent px-4 py-2 text-sm font-semibold text-panel-copy transition hover:border-brand/40 hover:text-brand"
                            onClick={() => setSelectedTriggerId(triggerReviewQueue[0]?.trigger_id ?? null)}
                          >
                            Review trigger
                          </button>
                        ) : null}
                      </div>
                    </Card>
                    {priorityWardPanel}
                  </>
                ) : (
                  <Card className="rounded-[1.5rem] p-4 shadow-none">
                    <p className="text-sm font-semibold text-panel-strong">No immediate action is recommended</p>
                    <p className="mt-2 text-sm text-panel-muted">{panelContext.recommendedAction}</p>
                  </Card>
                )}
              </div>
            ) : null}

            {activeSidebarTab === "triggers" ? (
              <div className="space-y-3">
                <div className="grid grid-cols-2 gap-3">
                  <div className="rounded-[1.1rem] border border-panel-table-wrap bg-panel/70 px-4 py-3">
                    <p className="text-xs font-semibold uppercase tracking-[0.14em] text-panel-muted">Review queue</p>
                    <strong className="mt-1 block text-2xl font-semibold text-panel-strong">{triggerReviewQueue.length}</strong>
                  </div>
                  <div className="rounded-[1.1rem] border border-panel-table-wrap bg-panel/70 px-4 py-3">
                    <p className="text-xs font-semibold uppercase tracking-[0.14em] text-panel-muted">Delivery concern</p>
                    <strong className="mt-1 block text-2xl font-semibold text-panel-strong">{triggerLinkage?.delivery_concern_wards_count ?? 0}</strong>
                  </div>
                </div>
                {triggerReviewQueue.length ? (
                  triggerReviewQueue.slice(0, 3).map((trigger: OverviewTriggerEvent) => (
                    <div key={trigger.trigger_id} className="rounded-[1.2rem] border border-panel-table-wrap bg-panel/70 px-4 py-4">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <strong className="block text-sm font-semibold text-panel-strong">{trigger.ward_name}</strong>
                          <p className="mt-1 text-sm text-panel-copy">{trigger.trend_label}</p>
                        </div>
                        <StatusBadge tone={trigger.risk_level === "HIGH" ? "danger" : trigger.risk_level === "MEDIUM" ? "warning" : "default"} className="rounded-full px-3 py-1 tracking-[0.14em]">
                          {trigger.confidence === "high" ? "High confidence" : trigger.confidence === "moderate" ? "Moderate confidence" : "Review"}
                        </StatusBadge>
                      </div>
                      <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-panel-muted">
                        <span>{trigger.predicted_cases} predicted cases</span>
                        <span>•</span>
                        <span>{trigger.alert_count} open alerts</span>
                      </div>
                    </div>
                  ))
                ) : (
                  <div className="rounded-[1.2rem] border border-dashed border-panel-table-wrap px-4 py-5 text-sm text-panel-muted">
                    No reviewable triggers are visible in the current dashboard scope.
                  </div>
                )}
              </div>
            ) : null}

            {activeSidebarTab === "readiness" ? (
              <div className="space-y-3">
                <div className="grid grid-cols-2 gap-3">
                  <div className="rounded-[1.1rem] border border-panel-table-wrap bg-panel/70 px-4 py-3">
                    <p className="text-xs font-semibold uppercase tracking-[0.14em] text-panel-muted">Facilities at risk</p>
                    <strong className="mt-1 block text-2xl font-semibold text-panel-strong">{facilityReadiness?.facilities_at_risk_count ?? 0}</strong>
                  </div>
                  <div className="rounded-[1.1rem] border border-panel-table-wrap bg-panel/70 px-4 py-3">
                    <p className="text-xs font-semibold uppercase tracking-[0.14em] text-panel-muted">Capacity concerns</p>
                    <strong className="mt-1 block text-2xl font-semibold text-panel-strong">{facilityReadiness?.facilities_capacity_concern_count ?? 0}</strong>
                  </div>
                </div>
                {facilityReadiness?.priority_facilities?.length ? (
                  facilityReadiness.priority_facilities.slice(0, 3).map((facility) => (
                    <div key={facility.facility_id} className="rounded-[1.2rem] border border-panel-table-wrap bg-panel/70 px-4 py-4">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <strong className="block text-sm font-semibold text-panel-strong">{facility.facility_name}</strong>
                          <p className="mt-1 text-sm text-panel-copy">{facility.ward_name}</p>
                        </div>
                        <StatusBadge tone={getFacilitySignalTone(facility.readiness_state)} className="rounded-full px-3 py-1 tracking-[0.14em]">
                          {formatFacilitySignalLabel(facility.readiness_state)}
                        </StatusBadge>
                      </div>
                    </div>
                  ))
                ) : (
                  <div className="rounded-[1.2rem] border border-dashed border-panel-table-wrap px-4 py-5 text-sm text-panel-muted">
                    No facility readiness concern is visible in the current scope.
                  </div>
                )}
                <Link
                  href="/facility-readiness"
                  className="inline-flex items-center gap-2 text-sm font-semibold text-brand transition hover:text-[var(--dashboard-icon-button-ink-hover)]"
                >
                  View facility readiness
                  <ArrowRight className="size-4" aria-hidden="true" />
                </Link>
              </div>
            ) : null}

            {activeSidebarTab === "scenarios" ? (
              <div className="space-y-3">
                <div className="rounded-[1.2rem] border border-panel-table-wrap bg-panel/70 px-4 py-4">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-[0.14em] text-panel-muted">Scenario tools</p>
                      <p className="mt-1 text-sm font-semibold text-panel-strong">
                        {simulationReadiness?.status_label ?? "Scenario simulation not live"}
                      </p>
                      <p className="mt-1 text-sm text-panel-copy">
                        Does not affect live risk, alerts, or trigger operations.
                      </p>
                    </div>
                    <StatusBadge tone={simulationReadiness?.supported ? "success" : "default"} className="rounded-full px-3 py-1 tracking-[0.14em]">
                      {simulationReadiness?.supported ? "Simulation only" : "Reserved"}
                    </StatusBadge>
                  </div>
                </div>

                <div className="space-y-3">
                  {simulationReadiness?.reserved_scenarios.map((scenario) => (
                    <div key={scenario.id} className="rounded-[1.2rem] border border-panel-table-wrap bg-panel/70 px-4 py-4">
                      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                        <div>
                          <strong className="block text-sm font-semibold text-panel-strong">{scenario.label}</strong>
                          <p className="mt-1 text-sm text-panel-copy">{scenario.prompt}</p>
                        </div>
                        <button
                          type="button"
                          disabled={simulationPending !== null}
                          aria-disabled={simulationPending !== null}
                          onClick={() => handleRunSimulation(scenario.id === "rainfall_increase" ? "RAINFALL_INCREASE" : "RESPONSE_DELAY")}
                          className="inline-flex h-10 items-center justify-center rounded-pill border border-brand bg-brand px-4 text-sm font-semibold text-white transition disabled:cursor-not-allowed disabled:opacity-70"
                        >
                          {simulationPending === (scenario.id === "rainfall_increase" ? "RAINFALL_INCREASE" : "RESPONSE_DELAY") ? "Running..." : "Run scenario"}
                        </button>
                      </div>
                    </div>
                  )) ?? null}
                </div>

                {simulationError ? (
                  <div className="rounded-[1.2rem] border border-[color:var(--danger)]/30 bg-[color-mix(in_srgb,var(--danger)_6%,white)] px-4 py-4 text-sm text-panel-copy">
                    {simulationError}
                  </div>
                ) : null}

                {simulationRun ? (
                  <div className="rounded-[1.2rem] border border-[color-mix(in_srgb,var(--brand)_20%,white)] bg-[color-mix(in_srgb,var(--brand)_6%,white)] px-4 py-4 dark:border-[color-mix(in_srgb,var(--brand)_24%,transparent)] dark:bg-[color-mix(in_srgb,var(--brand)_10%,transparent)]">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-panel-muted">Latest simulation result</p>
                        <p className="mt-1 text-sm font-semibold text-panel-strong">{simulationRun.summary.scenario_label}</p>
                      </div>
                      <StatusBadge tone="default" className="rounded-full px-3 py-1 tracking-[0.14em]">
                        Simulated result only
                      </StatusBadge>
                    </div>
                    <div className="mt-4 grid gap-3 rounded-[1.1rem] border border-panel-table-wrap/80 bg-panel/60 p-4 sm:grid-cols-2">
                      <div className="space-y-1">
                        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-panel-muted">
                          {scopedScenarioWardResult && topScenarioWardResult && scopedScenarioWardResult.ward_id !== topScenarioWardResult.ward_id
                            ? "Top impacted ward in this view"
                            : "Top impacted ward"}
                        </p>
                        <p className="text-sm font-semibold text-panel-strong">
                          {formatScenarioTopWardLabel((scopedScenarioWardResult ?? topScenarioWardResult)?.ward_name)}
                        </p>
                        {scopedScenarioWardResult && topScenarioWardResult && scopedScenarioWardResult.ward_id !== topScenarioWardResult.ward_id ? (
                          <p className="text-xs text-panel-muted">
                            Overall simulation impact extends beyond the current county scope.
                          </p>
                        ) : null}
                      </div>
                      <div className="space-y-1">
                        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-panel-muted">Run time</p>
                        <p className="text-sm text-panel-copy">{formatExactOperationalTimestamp(simulationRun.created_at)}</p>
                      </div>
                      <div className="space-y-1">
                        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-panel-muted">Predicted risk change</p>
                        <p className="text-sm text-panel-copy">
                          {(scopedScenarioWardResult ?? topScenarioWardResult)
                            ? formatScenarioDeltaSummary(
                                formatScenarioRiskDelta(
                                  (scopedScenarioWardResult ?? topScenarioWardResult)!.baseline_risk_score,
                                  (scopedScenarioWardResult ?? topScenarioWardResult)!.simulated_risk_score,
                                ),
                              )
                            : "No visible change in this scope"}
                        </p>
                      </div>
                      <div className="space-y-1">
                        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-panel-muted">Predicted case change</p>
                        <p className="text-sm text-panel-copy">
                          {(scopedScenarioWardResult ?? topScenarioWardResult)
                            ? formatScenarioDeltaSummary(
                                formatScenarioCaseDelta(
                                  (scopedScenarioWardResult ?? topScenarioWardResult)!.baseline_predicted_cases,
                                  (scopedScenarioWardResult ?? topScenarioWardResult)!.simulated_predicted_cases,
                                ),
                              )
                            : "No visible change in this scope"}
                        </p>
                      </div>
                    </div>
                    {(scopedScenarioWardResult ?? topScenarioWardResult) ? (
                      <div className="mt-4 flex flex-wrap gap-3">
                        <button
                          type="button"
                          className="inline-flex h-10 items-center justify-center rounded-pill bg-[linear-gradient(180deg,#1d6fda_0%,#175fc2_100%)] px-4 text-sm font-semibold text-white shadow-[0_16px_32px_rgba(23,95,194,0.18)] transition hover:-translate-y-px"
                          onClick={handlePreviewSimulationOnMap}
                        >
                          Preview on map
                        </button>
                      </div>
                    ) : null}
                  </div>
                ) : null}
              </div>
            ) : null}
          </Card>
        </aside>
      </section>

      <section className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(280px,0.42fr)]">
        <Card className="space-y-5 p-6">
          <PageSectionHeader
            title="Recent Alerts"
            description={`${overview?.primaryCountyLabel ?? "Current scope"} visible alert activity`}
          />

          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex flex-wrap items-center gap-2">
              {[
                { value: "ALL" as const, label: "All" },
                { value: "RETRY_PENDING" as const, label: "Retry pending" },
                { value: "DELIVERED" as const, label: "Delivered" },
                { value: "HIGH_RISK" as const, label: "High risk" },
              ].map((filter) => (
                <button
                  key={filter.value}
                  type="button"
                  className={`inline-flex h-9 items-center justify-center rounded-pill border px-3 text-sm font-semibold transition ${
                    recentAlertsFilter === filter.value
                      ? "border-brand bg-brand text-white"
                      : "border-panel-table-wrap bg-panel/70 text-panel-copy hover:border-brand/40 hover:text-panel-strong"
                  }`}
                  onClick={() => setRecentAlertsFilter(filter.value)}
                >
                  {filter.label}
                </button>
              ))}
            </div>

            <button
              type="button"
              className={`inline-flex h-9 items-center justify-center gap-2 rounded-pill border px-3.5 text-sm font-semibold transition ${
                activeIssuesOnly
                  ? "border-[color:var(--warning)] bg-[color-mix(in_srgb,var(--warning)_16%,transparent)] text-[color:var(--warning)] shadow-[0_10px_24px_rgba(245,158,11,0.14)]"
                  : "border-panel-table-wrap bg-panel/70 text-panel-copy hover:border-brand/40 hover:text-panel-strong"
              }`}
              onClick={() => setActiveIssuesOnly((currentValue) => !currentValue)}
              aria-pressed={activeIssuesOnly}
            >
              <AlertTriangle className="size-4" aria-hidden="true" />
              <span>Active issues only</span>
              <span className="text-[11px] uppercase tracking-[0.14em] opacity-80">{activeIssuesOnly ? "On" : "Off"}</span>
            </button>
          </div>

          {allVisibleAlertsAreStale ? (
            <div className="rounded-[1.1rem] border border-[color-mix(in_srgb,var(--warning)_24%,white)] bg-[color-mix(in_srgb,var(--warning)_8%,white)] px-4 py-3 text-sm text-panel-copy dark:border-[color-mix(in_srgb,var(--warning)_28%,transparent)] dark:bg-[color-mix(in_srgb,var(--warning)_12%,transparent)]">
              No recent alerts in last 48h.
            </div>
          ) : null}

          <div className="overflow-hidden rounded-[1.5rem] border border-[var(--dashboard-table-line)]">
            <div className="overflow-x-auto">
              <table className="min-w-full border-collapse text-left">
                <thead>
                  <tr>
                    {["Administrative ward", "Channel", "Risk Score", "Status", "Time", "Actions"].map((label) => (
                      <th
                        key={label}
                        className="border-b border-[var(--dashboard-table-line)] bg-[color-mix(in_srgb,var(--dashboard-table-line)_30%,transparent)] px-4 py-3 text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted"
                      >
                        <span
                          title={label === "Risk Score" ? "Composite risk score used to trigger alerts" : undefined}
                          className="inline-flex items-center"
                        >
                          {label}
                        </span>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {isLoading ? (
                    <tr>
                      <td colSpan={6} className="px-4 py-8 text-sm text-panel-muted">
                        Loading alert records...
                      </td>
                    </tr>
                  ) : recentAlertsRows.length > 0 ? (
                    recentAlertsRows.map((alert) => {
                      const isStale = isOperationallyStaleAlert(alert.created_at);
                      const wardCount = recentAlertWardCounts[alert.ward_name] ?? 1;

                      return (
                      <tr key={alert.id} className={isStale ? "opacity-70" : undefined}>
                        <td className="border-b border-[var(--dashboard-table-line)] px-4 py-4 text-sm last:border-b-0">
                          <div className="flex items-center gap-3">
                            <span
                              className={`inline-flex size-2.5 rounded-full ${getAlertRiskDotClass(deriveAlertRiskLevel(alert.risk_score))}`}
                              title={`${deriveAlertRiskLevel(alert.risk_score)} risk`}
                              aria-hidden="true"
                            />
                            <Link
                              href={`/alerts/${alert.id}`}
                              className="font-semibold text-panel-strong transition hover:text-brand"
                            >
                              {alert.ward_name}
                              {wardCount > 1 ? ` (${wardCount})` : ""}
                            </Link>
                          </div>
                        </td>
                        <td className="border-b border-[var(--dashboard-table-line)] px-4 py-4 text-sm text-panel-copy last:border-b-0">
                          {formatChannelLabel(alert.channel)}
                        </td>
                        <td className="border-b border-[var(--dashboard-table-line)] px-4 py-4 text-sm last:border-b-0">
                          {typeof alert.risk_score === "number" ? (
                            <span
                              className={`inline-flex rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-[0.14em] ${getScoreTone(alert.risk_score)}`}
                            >
                              {formatRiskScore(alert.risk_score)}
                            </span>
                          ) : (
                            <span className="text-panel-muted">N/A</span>
                          )}
                        </td>
                        <td className="border-b border-[var(--dashboard-table-line)] px-4 py-4 text-sm last:border-b-0">
                          <StatusBadge
                            tone={
                              alert.status === "DELIVERED"
                                ? "success"
                                : alert.status === "FAILED"
                                  ? "danger"
                                  : alert.status === "RETRY_PENDING"
                                    ? "warning"
                                    : "default"
                            }
                            className="rounded-full px-3 py-1 tracking-[0.14em]"
                          >
                            {formatStatusLabel(alert.status)}
                          </StatusBadge>
                        </td>
                        <td className="border-b border-[var(--dashboard-table-line)] px-4 py-4 text-sm text-panel-copy last:border-b-0">
                          <div className="space-y-1">
                            <span title={formatExactOperationalTimestamp(alert.created_at)}>
                              {formatRelativeOperationalAge(alert.created_at)}
                            </span>
                            {isStale ? (
                              <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-panel-muted">Stale</p>
                            ) : null}
                          </div>
                        </td>
                        <td className="border-b border-[var(--dashboard-table-line)] px-4 py-4 text-sm last:border-b-0">
                          <div className="flex flex-wrap items-center gap-3">
                            {alert.status === "RETRY_PENDING" ? (
                              <Link
                                href={`/alerts/${alert.id}`}
                                className="inline-flex h-8 items-center justify-center rounded-pill bg-[color:var(--warning)] px-3 text-xs font-semibold uppercase tracking-[0.14em] text-slate-950 transition hover:brightness-[1.04]"
                              >
                                Retry
                              </Link>
                            ) : null}
                            <Link
                              href={`/alerts/${alert.id}`}
                              className="text-xs font-semibold uppercase tracking-[0.14em] text-brand transition hover:text-[var(--dashboard-icon-button-ink-hover)]"
                            >
                              View alert
                            </Link>
                          </div>
                        </td>
                      </tr>
                    )})
                  ) : (
                    <tr>
                      <td colSpan={6} className="px-4 py-8 text-sm text-panel-muted">
                        No recent alerts. System operating normally.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          <div className="flex justify-end">
            <Link
              href="/alerts"
              className="inline-flex items-center gap-2 rounded-pill border border-brand/35 bg-[color-mix(in_srgb,var(--brand)_10%,white)] px-4 py-2 text-sm font-semibold text-brand transition hover:bg-[color-mix(in_srgb,var(--brand)_16%,white)] hover:text-[var(--dashboard-icon-button-ink-hover)]"
            >
              View all alerts
              <ArrowRight className="size-4" aria-hidden="true" />
            </Link>
          </div>
        </Card>

        <aside className="space-y-4">
          {(facilityReadiness?.facilities_at_risk_count ?? 0) > 0 || (facilityReadiness?.facilities_capacity_concern_count ?? 0) > 0 ? (
            <Card className="space-y-3 p-4">
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted">Facility readiness</p>
              <div className="flex flex-wrap items-center gap-3 text-sm text-panel-copy">
                <span>Facilities at risk: {facilityReadiness?.facilities_at_risk_count ?? 0}</span>
                <span>Capacity concerns: {facilityReadiness?.facilities_capacity_concern_count ?? 0}</span>
              </div>
              <Link
                href="/facility-readiness"
                className="inline-flex items-center gap-2 text-sm font-semibold text-brand transition hover:text-[var(--dashboard-icon-button-ink-hover)]"
              >
                View facility readiness
                <ArrowRight className="size-4" aria-hidden="true" />
              </Link>
            </Card>
          ) : null}

          <Card
            className={`space-y-3 border-panel-table-wrap/70 bg-panel/70 p-4 ${
              triggerSurfaceState.state === "action_required"
                ? "border-l-4 border-l-[color:var(--danger)] bg-[linear-gradient(135deg,color-mix(in_srgb,var(--danger)_6%,white),color-mix(in_srgb,var(--panel)_98%,transparent))] dark:bg-[linear-gradient(135deg,color-mix(in_srgb,var(--danger)_12%,transparent),color-mix(in_srgb,var(--panel)_94%,transparent))]"
                : ""
            }`}
          >
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted">Trigger state</p>
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                {triggerSurfaceState.state === "action_required" ? (
                  <AlertTriangle className="size-4.5 text-[color:var(--danger)]" aria-hidden="true" />
                ) : null}
                <p className="text-lg font-semibold text-panel-strong">{triggerSurfaceState.headline}</p>
              </div>
              <p className="text-sm text-panel-copy">{triggerSurfaceState.interpretation}</p>
            </div>
            <div className="space-y-2 text-sm text-panel-copy">
              <div className="flex items-center justify-between gap-3">
                <span>Workflow-active wards</span>
                <span className="font-semibold text-panel-strong">{triggerSurfaceState.triggerActiveCount}</span>
              </div>
              <div className="flex items-center justify-between gap-3">
                <span>Delivery concerns</span>
                <span className="font-semibold text-panel-strong">{triggerSurfaceState.deliveryConcernCount}</span>
              </div>
            </div>
            {triggerSurfaceState.state === "action_required" ? (
              <button
                type="button"
                className="inline-flex items-center gap-2 text-sm font-semibold text-brand transition hover:text-[var(--dashboard-icon-button-ink-hover)]"
                onClick={handleJumpToActionFocus}
              >
                Review trigger queue
                <ArrowRight className="size-4" aria-hidden="true" />
              </button>
            ) : null}
          </Card>
        </aside>
      </section>

    </div>
  );
}
