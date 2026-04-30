"use client";

import { useQuery } from "@tanstack/react-query";

import {
  fetchChvCoverageRequestsViaBff,
  type ChvCoverageRequestRecord,
} from "@/lib/dashboard";
import { queryKeys } from "@/lib/query-keys";

const LIVE_CHV_COVERAGE_REQUEST_STATUSES = new Set(["OPEN", "APPROVED", "IN_PROGRESS"]);

async function fetchAllCoverageRequestsForWard(wardId: number) {
  const results: ChvCoverageRequestRecord[] = [];
  let page = 1;

  while (true) {
    const response = await fetchChvCoverageRequestsViaBff(page === 1 ? { ward_id: wardId } : { ward_id: wardId, page });
    results.push(...response.results);
    if (!response.next) {
      break;
    }
    page += 1;
  }

  return results;
}

export function useLiveChvCoverageRequestForWardQuery({
  wardId,
  enabled = true,
}: {
  wardId: number | null;
  enabled?: boolean;
}) {
  return useQuery({
    queryKey: queryKeys.chvs.coverageRequests.list({
      ward_id: wardId ?? "pending",
      live_only: true,
    }),
    queryFn: async () => {
      if (!wardId) {
        throw new Error("A ward id is required.");
      }

      const requests = await fetchAllCoverageRequestsForWard(wardId);
      const liveRequests = requests.filter((requestRecord) =>
        LIVE_CHV_COVERAGE_REQUEST_STATUSES.has(requestRecord.status),
      );

      if (liveRequests.length === 0) {
        return null;
      }

      return liveRequests.reduce<ChvCoverageRequestRecord | null>((latest, requestRecord) => {
        if (!latest) {
          return requestRecord;
        }

        return new Date(requestRecord.created_at).getTime() > new Date(latest.created_at).getTime()
          ? requestRecord
          : latest;
      }, null);
    },
    enabled: enabled && Boolean(wardId),
  });
}
