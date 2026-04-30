"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import {
  fetchChvCoverageRequestFromAlertPrefillViaBff,
  type ChvCoverageRequestFromAlertPrefillPayload,
} from "@/lib/dashboard";
import { queryKeys } from "@/lib/query-keys";

export function useCreateChvCoverageRequestFromAlertMutation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (payload: ChvCoverageRequestFromAlertPrefillPayload) =>
      fetchChvCoverageRequestFromAlertPrefillViaBff(payload),
    onSuccess: async (result) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.chvs.root() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.chvs.coverageRequests.all() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.wards.all() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.alerts.all() }),
        result.existing_request
          ? queryClient.invalidateQueries({
              queryKey: queryKeys.chvs.coverageRequests.detail(result.existing_request.public_id),
            })
          : Promise.resolve(),
      ]);
    },
  });
}
