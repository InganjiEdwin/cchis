"use client";

import { useQuery } from "@tanstack/react-query";

import { fetchAlertByIdViaBff, type AlertRecord, type WardDetailSummary } from "@/lib/dashboard";
import { queryKeys } from "@/lib/query-keys";

type AlertDetailData = {
  alert: AlertRecord | null;
  wardDetail: WardDetailSummary | null;
};

type UseAlertDetailQueryParams = {
  alertId: number;
  enabled?: boolean;
};

export function useAlertDetailQuery({ alertId, enabled = true }: UseAlertDetailQueryParams) {
  return useQuery({
    queryKey: queryKeys.alerts.detail(alertId),
    queryFn: async (): Promise<AlertDetailData> => {
      return fetchAlertByIdViaBff(alertId);
    },
    enabled,
  });
}
