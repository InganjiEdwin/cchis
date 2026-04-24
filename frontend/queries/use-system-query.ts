"use client";

import { useQuery } from "@tanstack/react-query";

import { fetchSystemDataViaBff } from "@/lib/dashboard";
import { queryKeys } from "@/lib/query-keys";

export type SystemSnapshot = {
  visibleWards: number;
  visibleAlerts: number;
  latestRiskTimestamp: string | null;
  latestAlertTimestamp: string | null;
};

export function useSystemQuery({ enabled = true }: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: queryKeys.system.root(),
    queryFn: async (): Promise<SystemSnapshot> => {
      const data = await fetchSystemDataViaBff();

      const latestRiskTimestamp = data.latestRisks.reduce<string | null>((latest, item) => {
        if (!item.generated_at) {
          return latest;
        }

        if (!latest || new Date(item.generated_at).getTime() > new Date(latest).getTime()) {
          return item.generated_at;
        }

        return latest;
      }, null);

      const latestAlertTimestamp = data.alerts.results.reduce<string | null>((latest, item) => {
        if (!latest || new Date(item.created_at).getTime() > new Date(latest).getTime()) {
          return item.created_at;
        }

        return latest;
      }, null);

      return {
        visibleWards: data.wards.count,
        visibleAlerts: data.alerts.count,
        latestRiskTimestamp,
        latestAlertTimestamp,
      };
    },
    enabled,
  });
}
