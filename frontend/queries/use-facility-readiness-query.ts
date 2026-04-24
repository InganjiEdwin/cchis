"use client";

import { useQuery } from "@tanstack/react-query";

import {
  fetchAlertsDataViaBff,
  fetchWardRiskDataViaBff,
  type AlertRecord,
  type LatestWardRisk,
  type WardSummary,
} from "@/lib/dashboard";
import { queryKeys } from "@/lib/query-keys";

export type FacilityReadinessSnapshot = {
  wards: WardSummary[];
  risks: LatestWardRisk[];
  alerts: AlertRecord[];
};

export function useFacilityReadinessQuery({ enabled = true }: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: queryKeys.facilityReadiness.root(),
    queryFn: async (): Promise<FacilityReadinessSnapshot> => {
      const [wardData, alertData] = await Promise.all([
        fetchWardRiskDataViaBff({ county: "Migori", ordering: "-current_risk_score" }),
        fetchAlertsDataViaBff(),
      ]);

      return {
        wards: wardData.wards.results,
        risks: wardData.latestRisks,
        alerts: alertData.results,
      };
    },
    enabled,
  });
}
