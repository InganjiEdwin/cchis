"use client";

import { useQuery } from "@tanstack/react-query";

import {
  fetchAlertsDataViaBff,
  fetchFacilityByIdViaBff,
  fetchWardRiskDataViaBff,
  type AlertRecord,
  type FacilityRecord,
  type LatestWardRisk,
} from "@/lib/dashboard";
import { queryKeys } from "@/lib/query-keys";

export type FacilityDetailSnapshot = {
  facility: FacilityRecord | null;
  risks: LatestWardRisk[];
  alerts: AlertRecord[];
};

export function useFacilityDetailQuery(facilityId: number | null, { enabled = true }: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: queryKeys.facilityReadiness.detail(facilityId ?? "unknown"),
    queryFn: async (): Promise<FacilityDetailSnapshot> => {
      if (!facilityId) {
        return { facility: null, risks: [], alerts: [] };
      }

      const [facilityResponse, wardResponse, alertResponse] = await Promise.all([
        fetchFacilityByIdViaBff(facilityId),
        fetchWardRiskDataViaBff({ county: "Migori", ordering: "-current_risk_score" }),
        fetchAlertsDataViaBff(),
      ]);

      return {
        facility: facilityResponse.facility,
        risks: wardResponse.latestRisks,
        alerts: alertResponse.results,
      };
    },
    enabled: enabled && Boolean(facilityId),
  });
}
