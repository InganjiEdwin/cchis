"use client";

import { useQuery } from "@tanstack/react-query";

import {
  fetchAlertsDataViaBff,
  fetchFacilityByIdViaBff,
  fetchWardMapViaBff,
  fetchWardRiskDataViaBff,
  type AlertRecord,
  type FacilityRecord,
  type LatestWardRisk,
  type WardMapResponse,
} from "@/lib/dashboard";
import { queryKeys } from "@/lib/query-keys";

export type FacilityDetailSnapshot = {
  facility: FacilityRecord | null;
  risks: LatestWardRisk[];
  alerts: AlertRecord[];
  wardMap: WardMapResponse | null;
};

export function useFacilityDetailQuery(facilityId: number | null, { enabled = true }: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: queryKeys.facilityReadiness.detail(facilityId ?? "unknown"),
    queryFn: async (): Promise<FacilityDetailSnapshot> => {
      if (!facilityId) {
        return { facility: null, risks: [], alerts: [], wardMap: null };
      }

      const [facilityResponse, wardResponse, alertResponse, wardMap] = await Promise.all([
        fetchFacilityByIdViaBff(facilityId),
        fetchWardRiskDataViaBff({ county: "Migori", ordering: "-current_risk_score" }),
        fetchAlertsDataViaBff(),
        fetchWardMapViaBff(),
      ]);

      return {
        facility: facilityResponse.facility,
        risks: wardResponse.latestRisks,
        alerts: alertResponse.results,
        wardMap,
      };
    },
    enabled: enabled && Boolean(facilityId),
  });
}
