"use client";

import { useQuery } from "@tanstack/react-query";

import {
  fetchWardDetailViaBff,
  type AlertRecord,
  type RiskScoreRecord,
  type WardIntelligenceDriverItem,
  type WardIntelligenceFreshness,
  type WardIntelligenceGuidanceItem,
  type WardIntelligenceTrend,
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
  riskScore: number | null;
  predictedCases: number;
  updatedAt: string | null;
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
};

type UseWardDetailQueryParams = {
  wardId: number;
  enabled?: boolean;
};

export function useWardDetailQuery({ wardId, enabled = true }: UseWardDetailQueryParams) {
  return useQuery({
    queryKey: queryKeys.wards.detail(wardId),
    queryFn: async (): Promise<WardDetailState> => {
      const response = await fetchWardDetailViaBff(wardId);
      const riskHistory = response.risk_history;
      const relatedAlerts = response.related_alerts;

      return {
        wardId,
        wardName: response.ward.name,
        wardCode: response.ward.ward_code ?? null,
        county: response.ward.county,
        subCounty: response.ward.sub_county,
        riskLevel: response.current_risk.risk_level ?? response.ward.current_risk_level ?? "UNKNOWN",
        riskScore: response.current_risk.risk_score ?? response.ward.current_risk_score ?? null,
        predictedCases: response.current_risk.predicted_cases ?? response.ward.predicted_cases ?? 0,
        updatedAt:
          response.current_risk.generated_at ??
          response.ward.latest_generated_at ??
          response.ward.updated_at ??
          null,
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
      };
    },
    enabled,
  });
}
