"use client";

import { useQuery } from "@tanstack/react-query";

import {
  fetchAlertsDataViaBff,
  fetchChvDataViaBff,
  fetchWardRiskDataViaBff,
  type AlertRecord,
  type ChvRecord,
  type LatestWardRisk,
} from "@/lib/dashboard";
import { queryKeys } from "@/lib/query-keys";

export type ChvOperationsSnapshot = {
  chvs: ChvRecord[];
  latestRisks: LatestWardRisk[];
  alerts: AlertRecord[];
};

export function useChvOperationsQuery({ enabled = true }: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: queryKeys.chvs.root(),
    queryFn: async (): Promise<ChvOperationsSnapshot> => {
      const [chvResponse, wardResponse, alertResponse] = await Promise.all([
        fetchChvDataViaBff(),
        fetchWardRiskDataViaBff({ county: "Migori", ordering: "-current_risk_score" }),
        fetchAlertsDataViaBff(),
      ]);

      return {
        chvs: chvResponse.results,
        latestRisks: wardResponse.latestRisks,
        alerts: alertResponse.results,
      };
    },
    enabled,
  });
}
