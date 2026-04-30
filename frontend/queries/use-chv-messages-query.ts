"use client";

import { useQuery } from "@tanstack/react-query";

import { fetchChvMessagesViaBff } from "@/lib/dashboard";
import { queryKeys } from "@/lib/query-keys";

export function useChvMessagesQuery(publicId: string | null, { enabled = true }: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: queryKeys.chvs.messages(publicId ?? "pending"),
    queryFn: () => fetchChvMessagesViaBff(publicId ?? ""),
    enabled: enabled && Boolean(publicId),
    retry: false,
  });
}
