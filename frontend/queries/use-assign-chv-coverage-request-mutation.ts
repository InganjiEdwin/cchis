"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { assignChvCoverageRequestViaBff, type AssignChvCoverageRequestPayload } from "@/lib/dashboard";
import { queryKeys } from "@/lib/query-keys";

export function useAssignChvCoverageRequestMutation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      publicId,
      payload,
    }: {
      publicId: string;
      payload: AssignChvCoverageRequestPayload;
    }) => assignChvCoverageRequestViaBff(publicId, payload),
    onSuccess: async (result) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.chvs.root() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.chvs.coverageRequests.all() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.chvs.coverageRequests.detail(result.public_id) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.system.root() }),
      ]);
    },
  });
}
