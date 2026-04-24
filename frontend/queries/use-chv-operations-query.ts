"use client";

import { useQuery } from "@tanstack/react-query";

import {
  fetchAlertsDataViaBff,
  fetchChvOperationsDataViaBff,
  fetchWardMapViaBff,
  fetchWardRiskDataViaBff,
  type AlertRecord,
  type ChvOperationsRecord,
  type LatestWardRisk,
  type WardMapResponse,
} from "@/lib/dashboard";
import { queryKeys } from "@/lib/query-keys";

export type ChvOperationsSnapshot = {
  chvs: ChvOperationsRecord[];
  latestRisks: LatestWardRisk[];
  alerts: AlertRecord[];
  wardMap: WardMapResponse;
};

export function useChvOperationsQuery({ enabled = true }: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: queryKeys.chvs.root(),
    queryFn: async (): Promise<ChvOperationsSnapshot> => {
      const [chvResponse, wardResponse, alertResponse, wardMap] = await Promise.all([
        fetchChvOperationsDataViaBff(),
        fetchWardRiskDataViaBff({ county: "Migori", ordering: "-current_risk_score" }),
        fetchAlertsDataViaBff(),
        fetchWardMapViaBff(),
      ]);

      return {
        chvs: chvResponse,
        latestRisks: wardResponse.latestRisks,
        alerts: alertResponse.results,
        wardMap,
      };
    },
    enabled,
  });
}
