"use client";

import { useQuery } from "@tanstack/react-query";

import {
  fetchWardMapViaBff,
  fetchWardDetailViaBff,
  fetchPreparednessActionsViaBff,
  type AlertRecord,
  type PreparednessActionRecord,
  type RiskScoreRecord,
  type WardIntelligenceDriverItem,
  type WardIntelligenceFreshness,
  type WardIntelligenceGuidanceItem,
  type WardMapFeature,
  type WardIntelligenceTrend,
  type WardIntelligenceRouteResponse,
  type WardSpatialEvidence,
  type WardOperationalEvidence,
} from "@/lib/dashboard";
import { queryKeys } from "@/lib/query-keys";

export type WardRiskLevel = "LOW" | "MEDIUM" | "HIGH" | "UNKNOWN";

export type WardDetailState = {
  wardId: number;
  wardName: string;
  wardCode: string | null;
  county: string;
  subCounty: string;
  riskLevel: WardRiskLevel;
  triggerState: WardIntelligenceRouteResponse["header_context"]["trigger_state"];
  actionRequired: boolean;
  primaryCtaKind: WardIntelligenceRouteResponse["decision_summary"]["primary_cta_kind"];
  riskScore: number | null;
  predictedCases: number;
  updatedAt: string | null;
  lastAlertAt: string | null;
  source: string | null;
  modelVersion: string | null;
  modelRunStatus: string | null;
  trend: WardIntelligenceTrend;
  driverSummaryMode: string;
  guidanceSummaryMode: string;
  freshness: WardIntelligenceFreshness;
  driverItems: WardIntelligenceDriverItem[];
  guidanceItems: WardIntelligenceGuidanceItem[];
  riskHistory: RiskScoreRecord[];
  relatedAlerts: AlertRecord[];
  preparednessActions: PreparednessActionRecord[];
  wardMapFeature: WardMapFeature | null;
  spatialMapFeatures: WardMapFeature[];
  workflow: WardIntelligenceRouteResponse["workflow"];
  decisionSummary: WardIntelligenceRouteResponse["decision_summary"];
  headerContext: WardIntelligenceRouteResponse["header_context"];
  spatialEvidence: WardSpatialEvidence | null;
  operationalEvidence: WardOperationalEvidence | null;
};

type UseWardDetailQueryParams = {
  wardId: number;
  enabled?: boolean;
};

export function useWardDetailQuery({ wardId, enabled = true }: UseWardDetailQueryParams) {
  return useQuery({
    queryKey: queryKeys.wards.detail(wardId),
    queryFn: async (): Promise<WardDetailState> => {
      const [response, wardMap, preparednessActions] = await Promise.all([
        fetchWardDetailViaBff(wardId),
        fetchWardMapViaBff(),
        fetchPreparednessActionsViaBff({ ward_id: wardId, page_size: 100, ordering: "due_at" }),
      ]);
      const riskHistory = response.risk_history;
      const relatedAlerts = response.related_alerts;
      const wardMapFeature =
        wardMap.features.find((feature) => feature.properties.backend_ward_id === wardId) ?? null;
      const spatialEvidence = response.spatial_evidence ?? null;
      const spatialWardIds = new Set<number>([
        wardId,
        ...(spatialEvidence?.neighbors.map((neighbor) => neighbor.ward_id) ?? []),
      ]);
      const spatialMapFeatures = wardMap.features.filter(
        (feature) =>
          typeof feature.properties.backend_ward_id === "number" &&
          spatialWardIds.has(feature.properties.backend_ward_id),
      );
      const workflow = response.workflow ?? null;
      const triggerState = workflow?.status ?? "NONE";
      const headerContext = response.header_context ?? {
        last_alert_at: relatedAlerts[0]?.created_at ?? null,
        latest_record_at:
          response.current_risk.generated_at ??
          response.ward.latest_generated_at ??
          response.ward.updated_at ??
          null,
        freshness_state: response.freshness.is_stale ? ("STALE" as const) : ("FRESH" as const),
        trigger_state: triggerState,
        expected_cases_7d:
          response.current_risk.predicted_cases ??
          response.ward.predicted_cases ??
          0,
        risk_score:
          response.current_risk.risk_score ??
          response.ward.current_risk_score ??
          null,
      };
      const decisionSummary = response.decision_summary ?? {
        action_required: false,
        headline: "Ward decision summary unavailable.",
        why: "No operator decision summary is available from the current ward records.",
        next_steps: ["View full alert history"],
        primary_cta_kind: "VIEW_ALERT_HISTORY" as const,
      };

      return {
        wardId,
        wardName: response.ward.name,
        wardCode: response.ward.ward_code ?? null,
        county: response.ward.county,
        subCounty: response.ward.sub_county,
        triggerState: headerContext.trigger_state,
        actionRequired: decisionSummary.action_required,
        primaryCtaKind: decisionSummary.primary_cta_kind,
        riskLevel: response.current_risk.risk_level ?? response.ward.current_risk_level ?? "UNKNOWN",
        riskScore:
          headerContext.risk_score ??
          response.current_risk.risk_score ??
          response.ward.current_risk_score ??
          null,
        predictedCases:
          headerContext.expected_cases_7d ??
          response.current_risk.predicted_cases ??
          response.ward.predicted_cases ??
          0,
        updatedAt:
          headerContext.latest_record_at ??
          response.current_risk.generated_at ??
          response.ward.latest_generated_at ??
          response.ward.updated_at ??
          null,
        lastAlertAt: headerContext.last_alert_at,
        source: response.current_risk.source ?? response.ward.latest_source ?? null,
        modelVersion: response.current_risk.model_version ?? response.ward.latest_model_version ?? null,
        modelRunStatus: response.current_risk.model_run_status ?? null,
        trend: response.trend,
        driverSummaryMode: response.driver_summary.mode,
        guidanceSummaryMode: response.guidance_summary.mode,
        freshness: response.freshness,
        driverItems: response.driver_summary.items,
        guidanceItems: response.guidance_summary.items,
        riskHistory,
        relatedAlerts,
        preparednessActions: preparednessActions.results,
        wardMapFeature,
        spatialMapFeatures,
        workflow,
        decisionSummary,
        headerContext,
        spatialEvidence,
        operationalEvidence: response.operational_evidence ?? null,
      };
    },
    enabled,
  });
}
