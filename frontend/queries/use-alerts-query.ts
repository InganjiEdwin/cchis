"use client";

import { useQuery } from "@tanstack/react-query";

import { fetchAlertsDataViaBff, type AlertRecord } from "@/lib/dashboard";
import { queryKeys } from "@/lib/query-keys";

type UseAlertsQueryParams = {
  enabled?: boolean;
};

export function useAlertsQuery({ enabled = true }: UseAlertsQueryParams = {}) {
  return useQuery({
    queryKey: queryKeys.alerts.list({}),
    queryFn: async (): Promise<AlertRecord[]> => {
      const response = await fetchAlertsDataViaBff();
      return response.results;
    },
    enabled,
  });
}
