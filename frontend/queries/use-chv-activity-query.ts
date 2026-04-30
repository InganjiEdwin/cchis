"use client";

import { useQuery } from "@tanstack/react-query";

import { fetchChvActivityViaBff } from "@/lib/dashboard";
import { queryKeys } from "@/lib/query-keys";

export function useChvActivityQuery(publicId: string | null, { enabled = true }: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: queryKeys.chvs.activity(publicId ?? "pending"),
    queryFn: () => fetchChvActivityViaBff(publicId ?? ""),
    enabled: enabled && Boolean(publicId),
  });
}
