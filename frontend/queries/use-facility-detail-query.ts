"use client";

import { useQuery } from "@tanstack/react-query";

import {
  fetchFacilityByIdViaBff,
  fetchWardMapViaBff,
  type FacilityIntelligenceRouteResponse,
  type WardMapResponse,
} from "@/lib/dashboard";
import { queryKeys } from "@/lib/query-keys";

export type FacilityDetailSnapshot = {
  intelligence: FacilityIntelligenceRouteResponse | null;
  wardMap: WardMapResponse | null;
};

export function useFacilityDetailQuery(facilityId: number | null, { enabled = true }: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: queryKeys.facilityReadiness.detail(facilityId ?? "unknown"),
    queryFn: async (): Promise<FacilityDetailSnapshot> => {
      if (!facilityId) {
        return { intelligence: null, wardMap: null };
      }

      const [intelligence, wardMap] = await Promise.all([
        fetchFacilityByIdViaBff(facilityId),
        fetchWardMapViaBff(),
      ]);

      return {
        intelligence,
        wardMap,
      };
    },
    enabled: enabled && Boolean(facilityId),
  });
}
