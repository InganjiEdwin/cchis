"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  fetchPreparednessActionViaBff,
  fetchPreparednessActionsViaBff,
  updatePreparednessActionViaBff,
  type FetchPreparednessActionsParams,
  type PreparednessActionTransitionPayload,
} from "@/lib/dashboard";
import { queryKeys } from "@/lib/query-keys";

type UsePreparednessActionsQueryParams = {
  filters?: FetchPreparednessActionsParams;
  enabled?: boolean;
};

export function usePreparednessActionsQuery({
  filters = {},
  enabled = true,
}: UsePreparednessActionsQueryParams = {}) {
  return useQuery({
    queryKey: queryKeys.preparednessActions.list(filters),
    queryFn: () => fetchPreparednessActionsViaBff(filters),
    enabled,
  });
}

export function usePreparednessActionQuery(publicId: string | null, enabled = true) {
  return useQuery({
    queryKey: queryKeys.preparednessActions.detail(publicId ?? "none"),
    queryFn: () => {
      if (!publicId) {
        throw new Error("Preparedness action is required.");
      }
      return fetchPreparednessActionViaBff(publicId);
    },
    enabled: enabled && Boolean(publicId),
  });
}

export function useUpdatePreparednessActionMutation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({
      publicId,
      payload,
    }: {
      publicId: string;
      payload: PreparednessActionTransitionPayload;
    }) => updatePreparednessActionViaBff(publicId, payload),
    onSuccess: async (action) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.preparednessActions.root() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.preparednessActions.detail(action.public_id) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.wards.detail(action.ward) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.wards.all() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.overview.root() }),
      ]);
    },
  });
}
