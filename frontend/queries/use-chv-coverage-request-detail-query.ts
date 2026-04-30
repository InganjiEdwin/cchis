"use client";

import { useQuery } from "@tanstack/react-query";

import { fetchChvCoverageRequestDetailViaBff } from "@/lib/dashboard";
import { queryKeys } from "@/lib/query-keys";

export function useChvCoverageRequestDetailQuery({
  publicId,
  enabled = true,
}: {
  publicId: string | null;
  enabled?: boolean;
}) {
  return useQuery({
    queryKey: queryKeys.chvs.coverageRequests.detail(publicId ?? "pending"),
    queryFn: async () => {
      if (!publicId) {
        throw new Error("A CHV coverage request id is required.");
      }

      return fetchChvCoverageRequestDetailViaBff(publicId);
    },
    enabled: enabled && Boolean(publicId),
  });
}
