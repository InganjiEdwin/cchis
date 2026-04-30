"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { createChvMessageViaBff, type CreateChvMessagePayload } from "@/lib/dashboard";
import { queryKeys } from "@/lib/query-keys";

export function useCreateChvMessageMutation(publicId: string | null) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (payload: CreateChvMessagePayload) => {
      if (!publicId) {
        throw new Error("A CHV must be selected before sending a message.");
      }
      return createChvMessageViaBff(publicId, payload);
    },
    onSuccess: async () => {
      if (!publicId) {
        return;
      }
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.chvs.messages(publicId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.chvs.activity(publicId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.chvs.root() }),
      ]);
    },
  });
}
