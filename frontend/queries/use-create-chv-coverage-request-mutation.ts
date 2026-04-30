"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { createChvCoverageRequestViaBff, type CreateChvCoverageRequestPayload } from "@/lib/dashboard";
import { queryKeys } from "@/lib/query-keys";

export function useCreateChvCoverageRequestMutation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (payload: CreateChvCoverageRequestPayload) => createChvCoverageRequestViaBff(payload),
    onSuccess: async (result) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.chvs.root() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.chvs.coverageRequests.all() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.chvs.coverageRequests.detail(result.public_id) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.wards.all() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.system.root() }),
      ]);
    },
  });
}
