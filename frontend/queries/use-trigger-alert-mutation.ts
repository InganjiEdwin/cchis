"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { triggerAlertViaBff, type TriggerAlertRequest } from "@/lib/dashboard";
import { queryKeys } from "@/lib/query-keys";

export function useTriggerAlertMutation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (payload: TriggerAlertRequest) => triggerAlertViaBff(payload),
    onSuccess: async (_, variables) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.alerts.all() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.wards.all() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.wards.detail(variables.ward_id) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.chvs.root() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.facilityReadiness.root() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.overview.root() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.system.root() }),
      ]);
    },
  });
}
