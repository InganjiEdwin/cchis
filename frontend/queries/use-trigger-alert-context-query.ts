"use client";

import { useQuery } from "@tanstack/react-query";

import { fetchTriggerAlertContextViaBff } from "@/lib/dashboard";
import { queryKeys } from "@/lib/query-keys";

export function useTriggerAlertContextQuery(wardId: number | null, enabled = true) {
  return useQuery({
    queryKey: queryKeys.alerts.trigger.context(wardId ?? "none"),
    queryFn: async () => fetchTriggerAlertContextViaBff({ ward_id: wardId as number }),
    enabled: Boolean(wardId) && enabled,
  });
}
