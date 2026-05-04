"use client";

import { useQuery } from "@tanstack/react-query";

import {
  fetchOperationalKpiDashboardViaBff,
  type FetchOperationalKpiDashboardParams,
  type OperationalKpiDashboardResponse,
} from "@/lib/dashboard";
import { queryKeys } from "@/lib/query-keys";

export function useOperationalMetricsQuery(
  filters: FetchOperationalKpiDashboardParams = {},
  { enabled = true }: { enabled?: boolean } = {},
) {
  return useQuery({
    queryKey: queryKeys.operationalMetrics.dashboard(filters),
    queryFn: (): Promise<OperationalKpiDashboardResponse> => fetchOperationalKpiDashboardViaBff(filters),
    enabled,
  });
}
