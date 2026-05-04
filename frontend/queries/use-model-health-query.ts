"use client";

import { useQuery } from "@tanstack/react-query";

import {
  fetchModelOperationsHealthViaBff,
  type ModelOperationsHealthResponse,
} from "@/lib/dashboard";
import { queryKeys } from "@/lib/query-keys";

export function useModelOperationsHealthQuery() {
  return useQuery({
    queryKey: queryKeys.modelHealth.root(),
    queryFn: (): Promise<ModelOperationsHealthResponse> => fetchModelOperationsHealthViaBff(),
  });
}
