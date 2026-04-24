"use client";

import { useQuery } from "@tanstack/react-query";

import { fetchSession, type SessionResponse } from "@/lib/auth";
import { queryKeys } from "@/lib/query-keys";

type UseCurrentUserQueryParams = {
  enabled?: boolean;
  initialSession?: SessionResponse | null;
};

export function useCurrentUserQuery({
  enabled = true,
  initialSession = null,
}: UseCurrentUserQueryParams = {}) {
  return useQuery({
    queryKey: queryKeys.auth.me(),
    queryFn: fetchSession,
    enabled,
    initialData: initialSession ?? undefined,
    staleTime: 60 * 1000,
  });
}
