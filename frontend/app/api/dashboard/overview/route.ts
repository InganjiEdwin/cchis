import { NextResponse } from "next/server";

import type {
  AlertWorkflowRecord,
  AlertRecord,
  FacilityIntelligenceRouteResponse,
  FacilityRecord,
  IngestionRunRecord,
  LatestWardRisk,
  ModelRunRecord,
  OverviewFacilityReadinessState,
  OverviewFacilityReadinessSummary,
  OverviewFacilityWardSignal,
  OverviewPriorityFacility,
  OverviewMapGuidance,
  OverviewMapGuidanceTarget,
  OverviewMissionMetrics,
  OverviewSimulationReadiness,
  OverviewKpiTemporalDelta,
  OverviewTemporalMetrics,
  OverviewDecisionSummary,
  OverviewRuleBasis,
  OverviewStateModel,
  OverviewTriggeredWard,
  OverviewTriggerLinkageSummary,
  OverviewTriggerEvent,
  PaginatedResponse,
  RiskScoreRecord,
  WardMapResponse,
  WardSummary,
} from "@/lib/dashboard";
import { getPageWorkflowStateLabel, normalizeAlertWorkflowStatusToPageState } from "@/lib/dashboard";
import { ServerApiError, fetchBackendJson } from "@/lib/server-api";
import {
  buildFreshnessSummary,
  getLatestAlertTimestamp,
  getLatestDataSyncTimestamp,
  getLatestModelRunTimestamp,
  getLatestPredictionTimestamp,
} from "@/app/api/dashboard/_freshness";

function getOverviewWorkflowStateFromWorkflowStatus(
  status: AlertWorkflowRecord["status"] | null | undefined,
): OverviewTriggeredWard["workflow_state"] {
  return normalizeAlertWorkflowStatusToPageState(status);
}

function buildRuleBasis(ruleId: string, ruleLabel: string, inputs: string[]): OverviewRuleBasis {
  return {
    source: "bff_rules_v1",
    rule_id: ruleId,
    rule_label: ruleLabel,
    inputs,
  };
}

function buildOverviewState(latestRisks: LatestWardRisk[], alerts: AlertRecord[]): OverviewStateModel {
  const highRiskWards = latestRisks.filter((risk) => risk.risk_level === "HIGH");
  const underWatchWards = latestRisks.filter((risk) => risk.risk_level === "MEDIUM");
  const unresolvedAlerts = alerts.filter((alert) => alert.status !== "DELIVERED");
  const triggeredWardIds = new Set(unresolvedAlerts.map((alert) => alert.ward));
  const lastTriggeredAt =
    unresolvedAlerts
      .map((alert) => alert.created_at)
      .filter((timestamp): timestamp is string => Boolean(timestamp))
      .sort((left, right) => new Date(right).getTime() - new Date(left).getTime())[0] ?? null;

  let systemState: OverviewStateModel["system_state"] = "stable";
  let systemStateReason = "No elevated ward risk or visible trigger activity is present in the current dashboard scope.";

  if (highRiskWards.length > 0 || triggeredWardIds.size > 0) {
    systemState = "action_required";
    systemStateReason =
      highRiskWards.length > 0
        ? `${highRiskWards.length} ward${highRiskWards.length === 1 ? "" : "s"} currently sit in the high-risk band.`
        : `${triggeredWardIds.size} ward${triggeredWardIds.size === 1 ? "" : "s"} have unresolved alert activity that still needs review.`;
  } else if (underWatchWards.length > 0) {
    systemState = "watch";
    systemStateReason = `${underWatchWards.length} ward${underWatchWards.length === 1 ? "" : "s"} are under watch and need closer review.`;
  } else if (alerts.length > 0) {
    systemState = "watch";
    systemStateReason = "Recent alert history is visible, but no current high-risk or unresolved trigger condition is active.";
  }

  return {
    system_state: systemState,
    state_reason: systemStateReason,
    system_state_reason: systemStateReason,
    trigger_count: triggeredWardIds.size,
    watch_count: underWatchWards.length,
    action_required_count: highRiskWards.length,
    last_triggered_at: lastTriggeredAt,
    trigger_summary: {
      triggered_wards_count: triggeredWardIds.size,
      under_watch_wards_count: underWatchWards.length,
      action_required_wards_count: highRiskWards.length,
    },
    risk_state: {
      label:
        highRiskWards.length > 0
          ? "High-risk wards are visible."
          : underWatchWards.length > 0
            ? "Watch-level wards are visible."
            : "No elevated risk wards are visible.",
      high_risk_wards_count: highRiskWards.length,
      under_watch_wards_count: underWatchWards.length,
    },
    alert_state: {
      label:
        alerts.length > 0
          ? "Visible alert activity is present."
          : "No visible alert activity is present.",
      visible_alert_count: alerts.length,
      triggered_wards_count: triggeredWardIds.size,
    },
    action_state: {
      label:
        highRiskWards.length > 0
          ? "Escalate review and prepare response now."
          : underWatchWards.length > 0
            ? "Review watch wards and compare adjacent conditions."
            : "Continue routine monitoring.",
      recommended_mode: highRiskWards.length > 0 ? "act" : underWatchWards.length > 0 ? "review" : "monitor",
      action_required_wards_count: highRiskWards.length,
    },
  };
}

function buildDecisionSummary(latestRisks: LatestWardRisk[], alerts: AlertRecord[]): OverviewDecisionSummary {
  const unresolvedAlerts = alerts.filter((alert) => alert.status !== "DELIVERED");
  const alertCounts = alerts.reduce<Map<number, number>>((accumulator, alert) => {
    accumulator.set(alert.ward, (accumulator.get(alert.ward) ?? 0) + 1);
    return accumulator;
  }, new Map<number, number>());
  const unresolvedAlertWardIds = new Set(unresolvedAlerts.map((alert) => alert.ward));

  const rankedRisks = [...latestRisks].sort((left, right) => {
    const rightAlertPriority = unresolvedAlertWardIds.has(right.ward_id) ? 1 : 0;
    const leftAlertPriority = unresolvedAlertWardIds.has(left.ward_id) ? 1 : 0;
    if (rightAlertPriority !== leftAlertPriority) {
      return rightAlertPriority - leftAlertPriority;
    }

    const riskBandWeight = (risk: LatestWardRisk) =>
      risk.risk_level === "HIGH" ? 3 : risk.risk_level === "MEDIUM" ? 2 : risk.risk_level === "LOW" ? 1 : 0;
    const rightBand = riskBandWeight(right);
    const leftBand = riskBandWeight(left);
    if (rightBand !== leftBand) {
      return rightBand - leftBand;
    }

    return (right.risk_score ?? 0) - (left.risk_score ?? 0);
  });

  const topPriority = rankedRisks[0] ?? null;
  const nextWatchWard = rankedRisks.find((risk) => risk.risk_level === "MEDIUM") ?? null;

  if (!topPriority || (topPriority.risk_level !== "HIGH" && topPriority.risk_level !== "MEDIUM" && !unresolvedAlertWardIds.has(topPriority.ward_id))) {
    return {
      top_priority_ward: null,
      reason_flagged: nextWatchWard
        ? `${nextWatchWard.ward_name} is the next ward to monitor based on the latest watch-level signal.`
        : "No high-risk wards or unresolved trigger conditions are visible in the current dashboard scope.",
      recommended_action: nextWatchWard
        ? "Monitor the next watch-level ward and compare it with adjacent conditions."
        : "Continue routine monitoring and review recent activity for any early signal changes.",
      decision_mode: "risk_only",
      eligible_actions: ["investigate", "view_alerts"],
      rules_basis: nextWatchWard
        ? buildRuleBasis("watch_monitor_next_visible_ward", "Watch ward follow-up", [
            "latest visible watch-level ward",
            "no higher-priority unresolved alert in scope",
          ])
        : buildRuleBasis("stable_monitor_only", "Stable monitoring posture", [
            "no visible high-risk ward",
            "no unresolved trigger condition",
          ]),
    };
  }

  const hasUnresolvedAlert = unresolvedAlertWardIds.has(topPriority.ward_id);
  const alertCount = alertCounts.get(topPriority.ward_id) ?? 0;
  const decisionMode: OverviewDecisionSummary["decision_mode"] = hasUnresolvedAlert
    ? "triggered"
    : topPriority.risk_level === "HIGH"
      ? "risk_only"
      : "alert_active";

  const reasonFlagged = hasUnresolvedAlert
    ? `${topPriority.ward_name} has unresolved alert activity and still sits in the current decision surface.`
    : topPriority.risk_level === "HIGH"
      ? `${topPriority.ward_name} is the highest current risk ward in the visible scope.`
      : `${topPriority.ward_name} is the strongest watch-level candidate in the visible scope.`;

  const recommendedAction = hasUnresolvedAlert
    ? "Review active alerts, confirm field conditions, and prepare targeted follow-up."
    : topPriority.risk_level === "HIGH"
      ? "Open ward intelligence, investigate drivers, and decide whether to queue a response alert."
      : "Review the ward in detail and compare its signal with nearby wards before escalating.";

  return {
    top_priority_ward: {
      ward_id: topPriority.ward_id,
      ward_name: topPriority.ward_name,
      risk_level: topPriority.risk_level,
      risk_score: topPriority.risk_score,
      predicted_cases: topPriority.predicted_cases,
      alert_count: alertCount,
      has_active_alert: hasUnresolvedAlert,
      generated_at: topPriority.generated_at,
    },
    reason_flagged: reasonFlagged,
    recommended_action: recommendedAction,
    decision_mode: decisionMode,
    eligible_actions: hasUnresolvedAlert
      ? ["view_alerts", "investigate", "dispatch_chvs"]
      : topPriority.risk_level === "HIGH"
        ? ["investigate", "view_alerts", "send_message"]
        : ["investigate", "view_alerts"],
    rules_basis: hasUnresolvedAlert
      ? buildRuleBasis("unresolved_alert_priority", "Unresolved alert takes priority", [
          "unresolved alert activity",
          "ward remains in visible decision scope",
        ])
      : topPriority.risk_level === "HIGH"
        ? buildRuleBasis("highest_current_risk_priority", "Highest current risk ward", [
            "highest visible current risk band",
            "no unresolved alert ahead of it",
          ])
        : buildRuleBasis("watch_level_review_priority", "Watch-level review candidate", [
            "strongest visible watch-level ward",
            "no visible high-risk or unresolved alert ahead of it",
          ]),
  };
}

function buildTriggerReviewQueue(latestRisks: LatestWardRisk[], alerts: AlertRecord[]): OverviewTriggerEvent[] {
  const unresolvedAlerts = alerts.filter((alert) => alert.status !== "DELIVERED");
  const alertsByWard = unresolvedAlerts.reduce<Map<number, AlertRecord[]>>((accumulator, alert) => {
    const current = accumulator.get(alert.ward) ?? [];
    current.push(alert);
    accumulator.set(alert.ward, current);
    return accumulator;
  }, new Map<number, AlertRecord[]>());

  return [...latestRisks]
    .filter((risk) => risk.risk_level === "HIGH" || risk.risk_level === "MEDIUM" || alertsByWard.has(risk.ward_id))
    .sort((left, right) => {
      const rightHasAlert = alertsByWard.has(right.ward_id) ? 1 : 0;
      const leftHasAlert = alertsByWard.has(left.ward_id) ? 1 : 0;
      if (rightHasAlert !== leftHasAlert) {
        return rightHasAlert - leftHasAlert;
      }

      const rightBand = right.risk_level === "HIGH" ? 3 : right.risk_level === "MEDIUM" ? 2 : 1;
      const leftBand = left.risk_level === "HIGH" ? 3 : left.risk_level === "MEDIUM" ? 2 : 1;
      if (rightBand !== leftBand) {
        return rightBand - leftBand;
      }

      return (right.risk_score ?? 0) - (left.risk_score ?? 0);
    })
    .slice(0, 5)
    .map((risk) => {
      const wardAlerts = alertsByWard.get(risk.ward_id) ?? [];
      const hasActiveAlert = wardAlerts.length > 0;
      const riskScorePercent = risk.risk_score == null ? null : risk.risk_score <= 1 ? Math.round(risk.risk_score * 100) : Math.round(risk.risk_score);
      const reasonItems: OverviewTriggerEvent["trigger_reason_items"] = [];

      if (risk.risk_level === "HIGH") {
        reasonItems.push({
          label: "Threshold breach",
          detail: `${risk.ward_name} is currently in the promoted high-risk band.`,
          tone: "danger",
        });
      } else if (risk.risk_level === "MEDIUM") {
        reasonItems.push({
          label: "Watch escalation",
          detail: `${risk.ward_name} is currently at watch level and needs closer operator review.`,
          tone: "warning",
        });
      }

      if (riskScorePercent != null) {
        reasonItems.push({
          label: "Recorded risk score",
          detail: `The latest visible ward score is ${riskScorePercent}%.`,
          tone: risk.risk_level === "HIGH" ? "danger" : "info",
        });
      }

      if (hasActiveAlert) {
        reasonItems.push({
          label: "Recent alert activity",
          detail: `${wardAlerts.length} unresolved alert${wardAlerts.length === 1 ? "" : "s"} still require review in this ward.`,
          tone: "warning",
        });
      }

      const confidence: OverviewTriggerEvent["confidence"] =
        hasActiveAlert && risk.risk_level === "HIGH"
          ? "high"
          : risk.risk_level === "HIGH"
            ? "moderate"
            : "review";

      return {
        trigger_id: `ward-trigger:${risk.ward_id}`,
        ward_id: risk.ward_id,
        ward_name: risk.ward_name,
        risk_level: risk.risk_level,
        risk_score: risk.risk_score,
        predicted_cases: risk.predicted_cases,
        trend_label: hasActiveAlert
          ? "Alert activity still unresolved"
          : risk.risk_level === "HIGH"
            ? "High-risk threshold crossed"
            : "Watch signal rising",
        trigger_reason_items: reasonItems,
        confidence,
        triggered_at: wardAlerts[0]?.created_at ?? risk.generated_at,
        recommended_action: hasActiveAlert
          ? "Review active alerts, confirm field conditions, and decide whether to reinforce field follow-up."
          : risk.risk_level === "HIGH"
            ? "Review the ward now and decide whether to create an operational alert request."
            : "Review this watch-level ward and compare adjacent conditions before escalating.",
        rules_basis: hasActiveAlert
          ? buildRuleBasis("trigger_queue_existing_alert_followup", "Trigger queue with existing alert", [
              "unresolved alert already exists",
              "ward remains reviewable in current scope",
            ])
          : risk.risk_level === "HIGH"
            ? buildRuleBasis("trigger_queue_high_risk_review", "High-risk ward review before alerting", [
                "promoted high-risk threshold crossed",
                "human review required before response work",
              ])
            : buildRuleBasis("trigger_queue_watch_review", "Watch-level review before escalation", [
                "watch-level ward visible",
                "adjacent comparison still required",
              ]),
        expected_operational_effect: hasActiveAlert
          ? "Keeps the operator aligned with live alert activity and reduces duplicate escalation."
          : "Preserves a human-reviewed trigger path before the system creates response work.",
        dismissible: false,
        has_active_alert: hasActiveAlert,
        alert_count: wardAlerts.length,
        eligible_actions: hasActiveAlert
          ? ["view_alerts", "investigate", "dispatch_chvs"]
          : risk.risk_level === "HIGH"
            ? ["investigate", "view_alerts", "send_message"]
            : ["investigate", "view_alerts"],
        latest_risk_update_at: risk.generated_at,
      };
    });
}

function getTriggerSeverity(risk: LatestWardRisk, alertCount: number): OverviewTriggeredWard["trigger_severity"] {
  if (risk.risk_level === "HIGH" || alertCount > 0) {
    return "high";
  }
  if (risk.risk_level === "MEDIUM") {
    return "medium";
  }
  return "review";
}

function getAlertDeliveryState(wardAlerts: AlertRecord[]): OverviewTriggeredWard["alert_delivery_state"] {
  if (!wardAlerts.length) {
    return "awaiting_review";
  }
  if (wardAlerts.some((alert) => alert.status === "FAILED")) {
    return "triggered_failed";
  }
  if (wardAlerts.some((alert) => alert.status === "RETRY_PENDING")) {
    return "triggered_retry_pending";
  }
  if (wardAlerts.some((alert) => alert.status === "QUEUED")) {
    return "triggered_queued";
  }
  return "triggered_delivered";
}

function getAlertDeliveryLabel(state: OverviewTriggeredWard["alert_delivery_state"]) {
  if (state === "triggered_delivered") return "Triggered and delivered";
  if (state === "triggered_retry_pending") return "Triggered but retry pending";
  if (state === "triggered_failed") return "Triggered but failed";
  if (state === "triggered_queued") return "Triggered and queued";
  return "Trigger detected, awaiting alert request";
}

function buildTriggerReason(risk: LatestWardRisk, wardAlerts: AlertRecord[]) {
  if (wardAlerts.some((alert) => alert.status === "FAILED")) {
    return `${risk.ward_name} has a recorded trigger with at least one failed delivery attempt that still needs operator follow-up.`;
  }
  if (wardAlerts.some((alert) => alert.status === "RETRY_PENDING")) {
    return `${risk.ward_name} has a recorded trigger with delivery retry still pending.`;
  }
  if (wardAlerts.some((alert) => alert.status === "QUEUED")) {
    return `${risk.ward_name} has a recorded trigger and the alert is still queued for delivery.`;
  }
  if (wardAlerts.some((alert) => alert.status === "DELIVERED")) {
    return `${risk.ward_name} has a recorded trigger with at least one delivered alert in the current scope.`;
  }
  if (risk.risk_level === "HIGH") {
    return `${risk.ward_name} crossed the promoted high-risk threshold and is waiting for human confirmation.`;
  }
  if (risk.risk_level === "MEDIUM") {
    return `${risk.ward_name} is currently at watch level and should be reviewed before escalation.`;
  }
  return `${risk.ward_name} remains reviewable based on the latest visible trigger surface.`;
}

function buildRecommendedResponse(
  deliveryState: OverviewTriggeredWard["alert_delivery_state"],
  risk: LatestWardRisk,
) {
  if (deliveryState === "triggered_failed") {
    return "Inspect the failed alert record, confirm the recipient path, and decide whether to resend or escalate manually.";
  }
  if (deliveryState === "triggered_retry_pending") {
    return "Track the pending retry, confirm field conditions, and prepare a manual follow-up if delivery remains blocked.";
  }
  if (deliveryState === "triggered_queued") {
    return "Watch the queued alert until the first delivery attempt completes and avoid duplicating the response request.";
  }
  if (deliveryState === "triggered_delivered") {
    return "Review the delivered alert outcome, confirm the ward response, and watch for repeat escalation.";
  }
  if (risk.risk_level === "HIGH") {
    return "Review the ward now and decide whether to create an operational alert request.";
  }
  return "Review this watch-level ward and compare nearby conditions before escalating.";
}

function startOfToday() {
  const date = new Date();
  date.setHours(0, 0, 0, 0);
  return date;
}

function latestRiskCountsAtOrBeforeCutoff(riskScores: RiskScoreRecord[], scopedWardIds: Set<number>) {
  const latestByWard = new Map<number, RiskScoreRecord>();

  for (const score of riskScores) {
    if (!scopedWardIds.has(score.ward)) {
      continue;
    }
    if (!latestByWard.has(score.ward)) {
      latestByWard.set(score.ward, score);
    }
    if (latestByWard.size === scopedWardIds.size) {
      break;
    }
  }

  let high = 0;
  let medium = 0;
  for (const score of latestByWard.values()) {
    if (score.risk_level === "HIGH") {
      high += 1;
    } else if (score.risk_level === "MEDIUM") {
      medium += 1;
    }
  }

  return { high, medium };
}

function buildKpiTemporalDelta(currentValue: number, previousValue: number, contextLabel: string): OverviewKpiTemporalDelta {
  const delta = currentValue - previousValue;
  return {
    current_value: currentValue,
    previous_value: previousValue,
    delta,
    direction: delta > 0 ? "up" : delta < 0 ? "down" : "flat",
    context_label: contextLabel,
  };
}

function buildTemporalMetrics(
  latestRisks: LatestWardRisk[],
  previousRiskScores: RiskScoreRecord[],
  alertsToday: AlertRecord[],
  previousAlertsWindow: AlertRecord[],
  scopedWardIds: Set<number>,
): OverviewTemporalMetrics {
  const currentHigh = latestRisks.filter((risk) => risk.risk_level === "HIGH").length;
  const currentMedium = latestRisks.filter((risk) => risk.risk_level === "MEDIUM").length;
  const previousCounts = latestRiskCountsAtOrBeforeCutoff(previousRiskScores, scopedWardIds);

  const deliveredAlertRateCurrent = alertsToday.length
    ? Math.round((alertsToday.filter((alert) => alert.status === "DELIVERED").length / alertsToday.length) * 100)
    : 0;
  const deliveredAlertRatePrevious = previousAlertsWindow.length
    ? Math.round((previousAlertsWindow.filter((alert) => alert.status === "DELIVERED").length / previousAlertsWindow.length) * 100)
    : 0;

  return {
    high_risk: buildKpiTemporalDelta(currentHigh, previousCounts.high, "vs yesterday"),
    medium_risk: buildKpiTemporalDelta(currentMedium, previousCounts.medium, "vs yesterday"),
    alerts_today: buildKpiTemporalDelta(alertsToday.length, previousAlertsWindow.length, "vs previous 24h"),
    delivered_alert_rate: buildKpiTemporalDelta(
      deliveredAlertRateCurrent,
      deliveredAlertRatePrevious,
      "vs previous 24h",
    ),
  };
}

function formatLeadTimeLabel(hours: number | null) {
  if (hours == null) {
    return "No trigger yet";
  }
  if (hours < 1) {
    return "<1 hr";
  }
  if (hours < 24) {
    return `${Math.round(hours)} hr`;
  }
  const days = hours / 24;
  if (days < 10) {
    return `${Math.round(days)} d`;
  }
  return `${Math.round(days)} days`;
}

function buildMissionMetrics(
  workflows: AlertWorkflowRecord[],
  scopedWardIds: Set<number>,
): OverviewMissionMetrics {
  const scopedWorkflows = workflows.filter((workflow) => scopedWardIds.has(workflow.ward_id));
  const activeWorkflows = scopedWorkflows.filter((workflow) => workflow.status !== "RESOLVED");
  const latestTriggeredWorkflow =
    [...scopedWorkflows]
      .filter((workflow) => workflow.triggered_at)
      .sort((left, right) => new Date(right.triggered_at ?? 0).getTime() - new Date(left.triggered_at ?? 0).getTime())[0] ?? null;

  const latestLeadTimeWorkflow =
    [...scopedWorkflows]
      .filter((workflow) => workflow.triggered_at && workflow.latest_risk_update_at)
      .sort((left, right) => new Date(right.triggered_at ?? 0).getTime() - new Date(left.triggered_at ?? 0).getTime())[0] ?? null;

  const leadTimeHours =
    latestLeadTimeWorkflow && latestLeadTimeWorkflow.triggered_at && latestLeadTimeWorkflow.latest_risk_update_at
      ? Math.max(
          0,
          (new Date(latestLeadTimeWorkflow.triggered_at).getTime() - new Date(latestLeadTimeWorkflow.latest_risk_update_at).getTime()) /
            (1000 * 60 * 60),
        )
      : null;

  return {
    monitored_wards_count: scopedWardIds.size,
    workflow_active_wards_count: activeWorkflows.length,
    trigger_delivery_concern_count: activeWorkflows.filter(
      (workflow) =>
        workflow.alert_delivery_state === "triggered_retry_pending" || workflow.alert_delivery_state === "triggered_failed",
    ).length,
    last_trigger_lead_time_hours: leadTimeHours,
    last_trigger_lead_time_label: formatLeadTimeLabel(leadTimeHours),
    last_triggered_at: latestTriggeredWorkflow?.triggered_at ?? null,
    last_trigger_risk_signal_at: latestLeadTimeWorkflow?.latest_risk_update_at ?? null,
  };
}

function buildGuidanceTarget(
  risk: LatestWardRisk,
  alertCount: number,
  label: string,
  reason: string,
): OverviewMapGuidanceTarget {
  return {
    ward_id: risk.ward_id,
    ward_name: risk.ward_name,
    label,
    reason,
    risk_level: risk.risk_level,
    risk_score: risk.risk_score,
    alert_count: alertCount,
    predicted_cases: risk.predicted_cases,
  };
}

function buildMapGuidance(
  latestRisks: LatestWardRisk[],
  alerts: AlertRecord[],
  previousRiskScores: RiskScoreRecord[],
): OverviewMapGuidance {
  const alertsByWard = alerts.reduce<Map<number, AlertRecord[]>>((accumulator, alert) => {
    const current = accumulator.get(alert.ward) ?? [];
    current.push(alert);
    accumulator.set(alert.ward, current);
    return accumulator;
  }, new Map<number, AlertRecord[]>());
  const latestRiskByWard = new Map(latestRisks.map((risk) => [risk.ward_id, risk]));
  const previousByWard = new Map<number, RiskScoreRecord>();

  for (const score of previousRiskScores) {
    if (!previousByWard.has(score.ward)) {
      previousByWard.set(score.ward, score);
    }
  }

  const topTriggered = [...alertsByWard.entries()]
    .map(([wardId, wardAlerts]) => {
      const latestRisk = latestRiskByWard.get(wardId);
      if (!latestRisk) {
        return null;
      }
      return { latestRisk, wardAlerts };
    })
    .filter((item): item is { latestRisk: LatestWardRisk; wardAlerts: AlertRecord[] } => Boolean(item))
    .sort((left, right) => {
      if (right.wardAlerts.length !== left.wardAlerts.length) {
        return right.wardAlerts.length - left.wardAlerts.length;
      }
      return (right.latestRisk.risk_score ?? 0) - (left.latestRisk.risk_score ?? 0);
    })[0] ?? null;

  const mostActiveAlertWard = topTriggered;

  const biggestEscalation = latestRisks
    .map((risk) => {
      const previous = previousByWard.get(risk.ward_id);
      const previousScore = previous ? (previous.score <= 1 ? previous.score : previous.score / 100) : 0;
      const currentScore = risk.risk_score ?? 0;
      return {
        risk,
        delta: currentScore - previousScore,
      };
    })
    .sort((left, right) => right.delta - left.delta)[0] ?? null;

  const predictedHighestRisk = [...latestRisks].sort((left, right) => {
    const rightBand = right.risk_level === "HIGH" ? 3 : right.risk_level === "MEDIUM" ? 2 : 1;
    const leftBand = left.risk_level === "HIGH" ? 3 : left.risk_level === "MEDIUM" ? 2 : 1;
    if (rightBand !== leftBand) {
      return rightBand - leftBand;
    }
    if ((right.predicted_cases ?? 0) !== (left.predicted_cases ?? 0)) {
      return (right.predicted_cases ?? 0) - (left.predicted_cases ?? 0);
    }
    return (right.risk_score ?? 0) - (left.risk_score ?? 0);
  })[0] ?? null;

  return {
    top_triggered_ward: topTriggered
      ? buildGuidanceTarget(
          topTriggered.latestRisk,
          topTriggered.wardAlerts.length,
          "Top triggered ward",
          `${topTriggered.latestRisk.ward_name} has the strongest active trigger load in the current scope.`,
        )
      : null,
    most_active_alert_ward: mostActiveAlertWard
      ? buildGuidanceTarget(
          mostActiveAlertWard.latestRisk,
          mostActiveAlertWard.wardAlerts.length,
          "Most active alert ward",
          `${mostActiveAlertWard.wardAlerts.length} visible alert${mostActiveAlertWard.wardAlerts.length === 1 ? "" : "s"} currently cluster in ${mostActiveAlertWard.latestRisk.ward_name}.`,
        )
      : null,
    biggest_recent_escalation: biggestEscalation
      ? buildGuidanceTarget(
          biggestEscalation.risk,
          alertsByWard.get(biggestEscalation.risk.ward_id)?.length ?? 0,
          "Biggest recent escalation",
          `${biggestEscalation.risk.ward_name} shows the largest visible risk-score lift versus the prior daily window.`,
        )
      : null,
    predicted_highest_risk_ward: predictedHighestRisk
      ? buildGuidanceTarget(
          predictedHighestRisk,
          alertsByWard.get(predictedHighestRisk.ward_id)?.length ?? 0,
          "Predicted highest-risk ward",
          `${predictedHighestRisk.ward_name} currently leads the predicted hotspot surface.`,
        )
      : null,
  };
}

function readinessSeverity(state: OverviewFacilityReadinessState) {
  if (state === "capacity_concern") return 3;
  if (state === "watch") return 2;
  return 1;
}

function getFacilityReadinessState(facility: FacilityIntelligenceRouteResponse): OverviewFacilityReadinessState {
  if (facility.forecasting.projected_readiness_state === "capacity_concern" || facility.readiness.surge_risk === "EXTREME") {
    return "capacity_concern";
  }
  if (facility.forecasting.projected_readiness_state === "watch" || facility.readiness.surge_risk === "MODERATE") {
    return "watch";
  }
  return "ready";
}

function getFacilityReadinessScore(facility: FacilityIntelligenceRouteResponse, state: OverviewFacilityReadinessState) {
  if (facility.forecasting.projected_pressure_score > 0) {
    return facility.forecasting.projected_pressure_score;
  }
  if (state === "capacity_concern") return 90;
  if (state === "watch") return 60;
  return 25;
}

function buildFacilityReadinessSummary(
  facilityDetails: FacilityIntelligenceRouteResponse[],
): OverviewFacilityReadinessSummary {
  const priorityFacilities: OverviewPriorityFacility[] = facilityDetails
    .filter((detail): detail is FacilityIntelligenceRouteResponse & { facility: NonNullable<FacilityIntelligenceRouteResponse["facility"]> } => Boolean(detail.facility))
    .filter((detail) => detail.readiness.dashboard_truth_state !== "unavailable")
    .map((detail) => {
      const readinessState = getFacilityReadinessState(detail);
      return {
        facility_id: detail.facility.id,
        facility_name: detail.facility.name,
        ward_id: detail.facility.ward,
        ward_name: detail.facility.ward_name,
        readiness_state: readinessState,
        readiness_score: getFacilityReadinessScore(detail, readinessState),
        projected_pressure_score: detail.forecasting.projected_pressure_score,
        projected_case_burden: detail.readiness.projected_cases,
        driving_ward_ids: detail.context.driving_ward_ids,
        readiness_factors: detail.context.action_reasoning.slice(0, 2),
        snapshot_at: detail.readiness.last_reported_at,
        generated_at: detail.freshness.updated_at,
        freshness_state: detail.readiness.freshness_state,
        backing_source: detail.readiness.backing_source,
        dashboard_truth_state: detail.readiness.dashboard_truth_state,
      };
    })
    .sort((left, right) => {
      const severityDiff = readinessSeverity(right.readiness_state) - readinessSeverity(left.readiness_state);
      if (severityDiff !== 0) {
        return severityDiff;
      }
      if (right.projected_pressure_score !== left.projected_pressure_score) {
        return right.projected_pressure_score - left.projected_pressure_score;
      }
      return right.readiness_score - left.readiness_score;
    });

  const wardSignalsByWard = priorityFacilities.reduce<Map<number, OverviewFacilityWardSignal>>((accumulator, facility) => {
    const current = accumulator.get(facility.ward_id);
    const nextTone =
      facility.readiness_state === "capacity_concern"
        ? "danger"
        : facility.readiness_state === "watch"
          ? "warning"
          : "success";

    if (!current) {
      accumulator.set(facility.ward_id, {
        ward_id: facility.ward_id,
        ward_name: facility.ward_name,
        facility_capacity_signal: facility.readiness_state,
        facility_readiness_tone: nextTone,
        facility_count: 1,
        priority_facility_ids: [facility.facility_id],
        priority_facility_names: [facility.facility_name],
      });
      return accumulator;
    }

    accumulator.set(facility.ward_id, {
      ...current,
      facility_capacity_signal:
        readinessSeverity(facility.readiness_state) > readinessSeverity(current.facility_capacity_signal)
          ? facility.readiness_state
          : current.facility_capacity_signal,
      facility_readiness_tone:
        readinessSeverity(facility.readiness_state) > readinessSeverity(current.facility_capacity_signal)
          ? nextTone
          : current.facility_readiness_tone,
      facility_count: current.facility_count + 1,
      priority_facility_ids: [...current.priority_facility_ids, facility.facility_id].slice(0, 4),
      priority_facility_names: [...current.priority_facility_names, facility.facility_name].slice(0, 3),
    });
    return accumulator;
  }, new Map<number, OverviewFacilityWardSignal>());

  const anyProxy = priorityFacilities.some((facility) => facility.dashboard_truth_state !== "promoted_forecast");

  return {
    facilities_at_risk_count: priorityFacilities.filter((facility) => facility.readiness_state !== "ready").length,
    facilities_capacity_concern_count: priorityFacilities.filter((facility) => facility.readiness_state === "capacity_concern").length,
    priority_facilities: priorityFacilities.slice(0, 4),
    ward_capacity_signals: [...wardSignalsByWard.values()].sort(
      (left, right) => readinessSeverity(right.facility_capacity_signal) - readinessSeverity(left.facility_capacity_signal),
    ),
    honesty_note: priorityFacilities.length === 0
      ? "Facility readiness is withheld until a promoted facility forecast is available."
      : anyProxy
      ? "Some facility readiness signals are preview-backed and still blocked from promoted dashboard truth."
      : "Facility readiness signals shown here are backed by promoted facility-forecast outputs.",
  };
}

function buildSimulationReadiness(): OverviewSimulationReadiness {
  return {
    supported: true,
    status_label: "Scenario simulation available",
    status_reason:
      "The dashboard can now run bounded non-production scenarios without touching promoted live outputs.",
    required_contracts: [
      "Rainfall adjustment input contract",
      "Forecast perturbation input contract",
      "Predicted risk recomputation envelope",
      "Safe non-production execution and result-isolation rules",
    ],
    prepared_inputs: {
      rainfall_adjustments:
        "Would need bounded rainfall deltas or uplift factors tied to ward and time windows before recomputing downstream prediction surfaces.",
      forecast_perturbation_inputs:
        "Would need explicit non-production knobs for response delay, delivery latency, or facility pressure assumptions with audit metadata.",
      predicted_risk_recomputation_envelope:
        "Would need a temporary recomputation path that cannot overwrite promoted live outputs or confuse dashboard truth labels.",
      safe_non_production_execution_rules:
        "Would need user-visible non-production labeling, short-lived results, access control, and no persistence into promoted operational records.",
    },
    reserved_scenarios: [
      {
        id: "rainfall_increase",
        label: "What if rainfall increases?",
        prompt: "Explore how a bounded rainfall increase could alter predicted risk without touching live outputs.",
      },
      {
        id: "response_delay",
        label: "What if response is delayed?",
        prompt: "Explore how delayed response or delivery friction could change operational pressure and follow-up needs.",
      },
    ],
  };
}

function buildDecisionSummaryFromWorkflows(workflows: AlertWorkflowRecord[]): OverviewDecisionSummary {
  const topWorkflow = workflows[0] ?? null;
  if (!topWorkflow) {
    return {
      top_priority_ward: null,
      reason_flagged: "No high-risk wards or unresolved trigger conditions are visible in the current dashboard scope.",
      recommended_action: "Continue routine monitoring and review recent activity for any early signal changes.",
      decision_mode: "risk_only",
      eligible_actions: ["investigate", "view_alerts"],
      rules_basis: {
        source: "bff_rules_v1",
        rule_id: "stable_monitor_only",
        rule_label: "Stable monitoring posture",
        inputs: ["no visible workflow-backed trigger", "no current unresolved high-risk workflow"],
      },
    };
  }

  return {
    top_priority_ward: {
      ward_id: topWorkflow.ward_id,
      ward_name: topWorkflow.ward_name,
      risk_level: topWorkflow.risk_level,
      risk_score: topWorkflow.risk_score,
      predicted_cases: topWorkflow.predicted_cases,
      alert_count: topWorkflow.active_alert_count,
      has_active_alert: topWorkflow.active_alert_count > 0,
      generated_at: topWorkflow.latest_risk_update_at,
    },
    reason_flagged: topWorkflow.reason_flagged,
    recommended_action: topWorkflow.recommended_action,
    decision_mode: topWorkflow.decision_mode,
    eligible_actions: topWorkflow.eligible_actions,
    rules_basis: topWorkflow.rules_basis,
  };
}

function buildTriggerReviewQueueFromWorkflows(workflows: AlertWorkflowRecord[]): OverviewTriggerEvent[] {
  return workflows
    .filter((workflow) => workflow.status !== "RESOLVED")
    .slice(0, 5)
    .map((workflow) => ({
      trigger_id: `workflow:${workflow.public_id}`,
      ward_id: workflow.ward_id,
      ward_name: workflow.ward_name,
      risk_level: workflow.risk_level,
      risk_score: workflow.risk_score,
      predicted_cases: workflow.predicted_cases,
      trend_label: workflow.trigger_reason,
      trigger_reason_items: workflow.trigger_reason_items,
      confidence: workflow.confidence,
      triggered_at: workflow.triggered_at,
      recommended_action: workflow.recommended_action,
      rules_basis: workflow.rules_basis,
      expected_operational_effect: workflow.expected_operational_effect,
      dismissible: false,
      has_active_alert: workflow.active_alert_count > 0,
      alert_count: workflow.active_alert_count,
      eligible_actions: workflow.eligible_actions,
      latest_risk_update_at: workflow.latest_risk_update_at,
    }));
}

function buildTriggeredWardLinkageFromWorkflows(workflows: AlertWorkflowRecord[]): OverviewTriggerLinkageSummary {
  const triggeredWards = workflows
    .filter((workflow) => workflow.status !== "RESOLVED")
    .map((workflow) => {
      const workflowState = getOverviewWorkflowStateFromWorkflowStatus(workflow.status);

      return {
        ward_id: workflow.ward_id,
        ward_name: workflow.ward_name,
        risk_level: workflow.risk_level,
        risk_score: workflow.risk_score,
        predicted_cases: workflow.predicted_cases,
        trigger_reason: workflow.trigger_reason,
        trigger_severity: workflow.trigger_severity,
        triggered_at: workflow.triggered_at,
        recommended_response: workflow.recommended_response,
        rules_basis: workflow.rules_basis,
        workflow_state: workflowState,
        workflow_state_label: getPageWorkflowStateLabel(workflowState),
        alert_delivery_state: workflow.alert_delivery_state,
        alert_delivery_label: workflow.alert_delivery_label,
        alert_count: workflow.active_alert_count,
        delivered_alert_count: workflow.delivered_alert_count,
        retry_pending_alert_count: workflow.retry_pending_alert_count,
        failed_alert_count: workflow.failed_alert_count,
        queued_alert_count: workflow.queued_alert_count,
      };
    });

  return {
    triggered_wards: triggeredWards,
    active_alert_wards_count: triggeredWards.filter((item) => item.alert_count > 0).length,
    delivered_wards_count: triggeredWards.filter((item) => item.alert_delivery_state === "triggered_delivered").length,
    retry_pending_wards_count: triggeredWards.filter((item) => item.alert_delivery_state === "triggered_retry_pending").length,
    failed_wards_count: triggeredWards.filter((item) => item.alert_delivery_state === "triggered_failed").length,
    awaiting_review_wards_count: triggeredWards.filter((item) => item.alert_delivery_state === "awaiting_review").length,
    delivery_concern_wards_count: triggeredWards.filter((item) =>
      item.alert_delivery_state === "triggered_retry_pending" || item.alert_delivery_state === "triggered_failed",
    ).length,
  };
}

export async function GET(request: Request) {
  const cookieHeader = request.headers.get("cookie") ?? "";

  try {
    const now = new Date();
    const todayStart = startOfToday();
    const yesterdayCutoff = new Date(now.getTime() - 24 * 60 * 60 * 1000);
    const previousWindowStart = new Date(todayStart.getTime() - 24 * 60 * 60 * 1000);

    const [wards, latestRisks, alerts, wardMap, modelRuns, ingestionRuns, previousRiskScores, alertsTodayWindow, previousAlertsWindow, facilities, workflows] = await Promise.all([
      fetchBackendJson<PaginatedResponse<WardSummary>>("/wards/?page_size=100&ordering=name&county=Migori", {
        cookieHeader,
      }),
      fetchBackendJson<LatestWardRisk[]>("/risk-score/latest/", {
        cookieHeader,
      }),
      fetchBackendJson<PaginatedResponse<AlertRecord>>("/alerts/?page_size=100&ordering=-created_at", {
        cookieHeader,
      }),
      fetchBackendJson<WardMapResponse>("/maps/wards/", {
        cookieHeader,
      }),
      fetchBackendJson<PaginatedResponse<ModelRunRecord>>("/model-runs/?page_size=1&ordering=-completed_at", {
        cookieHeader,
      }),
      fetchBackendJson<PaginatedResponse<IngestionRunRecord>>("/ingestion-runs/?page_size=1&ordering=-started_at", {
        cookieHeader,
      }),
      fetchBackendJson<PaginatedResponse<RiskScoreRecord>>(
        `/risk-scores/?page_size=100&ordering=-generated_at&generated_before=${encodeURIComponent(yesterdayCutoff.toISOString())}`,
        {
          cookieHeader,
        },
      ),
      fetchBackendJson<PaginatedResponse<AlertRecord>>(
        `/alerts/?page_size=100&ordering=-created_at&created_after=${encodeURIComponent(todayStart.toISOString())}`,
        {
          cookieHeader,
        },
      ),
      fetchBackendJson<PaginatedResponse<AlertRecord>>(
        `/alerts/?page_size=100&ordering=-created_at&created_after=${encodeURIComponent(previousWindowStart.toISOString())}&created_before=${encodeURIComponent(todayStart.toISOString())}`,
        {
          cookieHeader,
        },
      ),
      fetchBackendJson<PaginatedResponse<FacilityRecord>>("/facilities/?page_size=100&ordering=ward__name,name", {
        cookieHeader,
      }),
      fetchBackendJson<{ count: number; results: AlertWorkflowRecord[] }>("/alerts/workflows/", {
        cookieHeader,
      }),
    ]);

    const scopedWardIds = new Set(wards.results.map((ward) => ward.id));
    const scopedLatestRisks = latestRisks.filter((risk) => scopedWardIds.has(risk.ward_id));
    const scopedAlerts = alerts.results.filter((alert) => scopedWardIds.has(alert.ward));
    const scopedWorkflows = workflows.results.filter((workflow) => scopedWardIds.has(workflow.ward_id));
    const overviewState = buildOverviewState(scopedLatestRisks, scopedAlerts);
    const decisionSummary = buildDecisionSummaryFromWorkflows(scopedWorkflows);
    const triggerReviewQueue = buildTriggerReviewQueueFromWorkflows(scopedWorkflows);
    const freshness = buildFreshnessSummary(
      getLatestModelRunTimestamp(modelRuns.results),
      getLatestDataSyncTimestamp(ingestionRuns.results),
      getLatestAlertTimestamp(scopedAlerts),
      getLatestPredictionTimestamp(scopedLatestRisks),
    );
    const triggerLinkage = buildTriggeredWardLinkageFromWorkflows(scopedWorkflows);
    const temporalMetrics = buildTemporalMetrics(
      scopedLatestRisks,
      previousRiskScores.results,
      alertsTodayWindow.results.filter((alert) => scopedWardIds.has(alert.ward)),
      previousAlertsWindow.results.filter((alert) => scopedWardIds.has(alert.ward)),
      scopedWardIds,
    );
    const missionMetrics = buildMissionMetrics(workflows.results, scopedWardIds);
    const mapGuidance = buildMapGuidance(scopedLatestRisks, scopedAlerts, previousRiskScores.results);
    const simulationReadiness = buildSimulationReadiness();
    const scopedFacilities = facilities.results.filter((facility) => scopedWardIds.has(facility.ward));
    const facilityDetails = await Promise.all(
      scopedFacilities.map((facility) =>
        fetchBackendJson<FacilityIntelligenceRouteResponse>(`/facilities/${facility.id}/intelligence/`, {
          cookieHeader,
        }),
      ),
    );
    const facilityReadiness = buildFacilityReadinessSummary(facilityDetails);

    return NextResponse.json({
      wards,
      latestRisks: scopedLatestRisks,
      alerts: {
        count: scopedAlerts.length,
        next: null,
        previous: null,
        results: scopedAlerts,
      },
      wardMap,
      overviewState,
      decisionSummary,
      triggerReviewQueue,
      freshness,
      temporalMetrics,
      missionMetrics,
      mapGuidance,
      triggerLinkage,
      facilityReadiness,
      simulationReadiness,
      alertWorkflows: scopedWorkflows,
    });
  } catch (error) {
    if (error instanceof ServerApiError) {
      return NextResponse.json({ detail: error.message }, { status: error.status });
    }

    return NextResponse.json({ detail: "Unable to load overview data." }, { status: 500 });
  }
}
