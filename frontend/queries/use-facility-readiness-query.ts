"use client";

import { useQuery } from "@tanstack/react-query";

import {
  fetchAlertsDataViaBff,
  fetchFacilityDataViaBff,
  fetchWardRiskDataViaBff,
  type AlertRecord,
  type FacilityRecord,
  type FacilityReadinessDecisionSummary,
  type FacilityReadinessWorkflowState,
  type LatestWardRisk,
} from "@/lib/dashboard";
import { queryKeys } from "@/lib/query-keys";

export type FacilityReadinessSnapshot = {
  facilities: FacilityRecord[];
  risks: LatestWardRisk[];
  alerts: AlertRecord[];
  decisionSummary: FacilityReadinessDecisionSummary | null;
  workflowStates: FacilityReadinessWorkflowState[];
};

export function useFacilityReadinessQuery({ enabled = true }: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: queryKeys.facilityReadiness.root(),
    queryFn: async (): Promise<FacilityReadinessSnapshot> => {
      const [facilityData, wardData, alertData] = await Promise.all([
        fetchFacilityDataViaBff(),
        fetchWardRiskDataViaBff({ county: "Migori", ordering: "-current_risk_score" }),
        fetchAlertsDataViaBff(),
      ]);

      return {
        facilities: facilityData.results,
        risks: wardData.latestRisks,
        alerts: alertData.results,
        decisionSummary: facilityData.decision_summary ?? null,
        workflowStates: facilityData.workflow_states ?? [],
      };
    },
    enabled,
  });
}
