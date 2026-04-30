import { useQuery } from "@tanstack/react-query";

import { fetchTriggerAlertRequestStatusViaBff } from "@/lib/dashboard";
import { queryKeys } from "@/lib/query-keys";

export function useTriggerAlertRequestStatusQuery(requestId: string | null, enabled: boolean) {
  return useQuery({
    queryKey: requestId ? queryKeys.alerts.trigger.requestStatus(requestId) : ["alerts", "trigger", "request-status", "idle"],
    queryFn: async () => {
      if (!requestId) {
        throw new Error("Request tracking is unavailable.");
      }
      return fetchTriggerAlertRequestStatusViaBff(requestId);
    },
    enabled: enabled && Boolean(requestId),
    refetchInterval: (query) => (query.state.data?.alert_id ? false : 3000),
  });
}
