"use client";

import { useQuery } from "@tanstack/react-query";

import {
  fetchAlertsDataViaBff,
  fetchChvDataViaBff,
  fetchWardMapViaBff,
  fetchWardRiskDataViaBff,
  type AlertRecord,
  type ChvRecord,
  type LatestWardRisk,
  type WardMapResponse,
} from "@/lib/dashboard";
import { queryKeys } from "@/lib/query-keys";

export type ChvOperationsSnapshot = {
  chvs: ChvRecord[];
  latestRisks: LatestWardRisk[];
  alerts: AlertRecord[];
  wardMap: WardMapResponse;
};

export function useChvOperationsQuery({ enabled = true }: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: queryKeys.chvs.root(),
    queryFn: async (): Promise<ChvOperationsSnapshot> => {
      const [chvResponse, wardResponse, alertResponse, wardMap] = await Promise.all([
        fetchChvDataViaBff(),
        fetchWardRiskDataViaBff({ county: "Migori", ordering: "-current_risk_score" }),
        fetchAlertsDataViaBff(),
        fetchWardMapViaBff(),
      ]);

      return {
        chvs: chvResponse.results,
        latestRisks: wardResponse.latestRisks,
        alerts: alertResponse.results,
        wardMap,
      };
    },
    enabled,
  });
}
