"use client";

import { useQuery } from "@tanstack/react-query";

import { fetchWardDetailViaBff, type AlertRecord, type RiskScoreRecord } from "@/lib/dashboard";
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
      const riskHistory = response.riskHistory.results;
      const relatedAlerts = response.alerts.results;
      const latestHistory = riskHistory[0] ?? null;

      return {
        wardId,
        wardName: response.ward.name,
        wardCode: response.ward.ward_code ?? null,
        county: response.ward.county,
        subCounty: response.ward.sub_county,
        riskLevel: latestHistory?.risk_level ?? response.ward.current_risk_level ?? "UNKNOWN",
        riskScore: latestHistory?.score ?? response.ward.current_risk_score ?? null,
        predictedCases: latestHistory?.predicted_cases ?? response.ward.predicted_cases ?? 0,
        updatedAt:
          latestHistory?.generated_at ??
          response.ward.latest_generated_at ??
          response.ward.updated_at ??
          null,
        source: latestHistory?.source ?? response.ward.latest_source ?? null,
        modelVersion: latestHistory?.model_version ?? response.ward.latest_model_version ?? null,
        riskHistory,
        relatedAlerts,
      };
    },
    enabled,
  });
}
