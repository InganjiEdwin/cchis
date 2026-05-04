"use client";

import { useQuery } from "@tanstack/react-query";

import {
  fetchAlertsDataViaBff,
  fetchChvCoverageRequestsViaBff,
  fetchChvOfflineMonitoringViaBff,
  fetchChvOperationsDataViaBff,
  fetchWardMapViaBff,
  fetchWardRiskDataViaBff,
  type AlertRecord,
  type ChvCoverageRequestRecord,
  type ChvOfflineMonitoringSnapshot,
  type ChvOperationsRecord,
  type LatestWardRisk,
  type WardMapResponse,
} from "@/lib/dashboard";
import { queryKeys } from "@/lib/query-keys";

export type ChvCoverageWardSummary = {
  wardId: number;
  liveRequestCount: number;
  overdueRequestCount: number;
  activeAssignmentCount: number;
  latestRequest: ChvCoverageRequestRecord | null;
};

export type ChvOperationsSnapshot = {
  chvs: ChvOperationsRecord[];
  latestRisks: LatestWardRisk[];
  alerts: AlertRecord[];
  wardMap: WardMapResponse;
  coverageRequests: ChvCoverageRequestRecord[];
  coverageByWard: Record<number, ChvCoverageWardSummary>;
  offlineMonitoring: ChvOfflineMonitoringSnapshot;
};

const LIVE_CHV_COVERAGE_REQUEST_STATUSES = new Set(["OPEN", "APPROVED", "IN_PROGRESS"]);

async function fetchAllCoverageRequests() {
  const results: ChvCoverageRequestRecord[] = [];
  let page = 1;

  while (true) {
    const response = await fetchChvCoverageRequestsViaBff(page === 1 ? {} : { page });
    results.push(...response.results);
    if (!response.next) {
      break;
    }
    page += 1;
  }

  return results;
}

export function useChvOperationsQuery({ enabled = true }: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: queryKeys.chvs.root(),
    queryFn: async (): Promise<ChvOperationsSnapshot> => {
      const [chvResponse, wardResponse, alertResponse, wardMap, coverageRequests, offlineMonitoring] = await Promise.all([
        fetchChvOperationsDataViaBff(),
        fetchWardRiskDataViaBff({ county: "Migori", ordering: "-current_risk_score" }),
        fetchAlertsDataViaBff(),
        fetchWardMapViaBff(),
        fetchAllCoverageRequests(),
        fetchChvOfflineMonitoringViaBff(),
      ]);

      const coverageByWard = coverageRequests.reduce<Record<number, ChvCoverageWardSummary>>(
        (accumulator, requestRecord) => {
          const summary = accumulator[requestRecord.ward] ?? {
            wardId: requestRecord.ward,
            liveRequestCount: 0,
            overdueRequestCount: 0,
            activeAssignmentCount: 0,
            latestRequest: null,
          };

          if (LIVE_CHV_COVERAGE_REQUEST_STATUSES.has(requestRecord.status)) {
            summary.liveRequestCount += 1;
          }
          if (requestRecord.is_overdue) {
            summary.overdueRequestCount += 1;
          }

          summary.activeAssignmentCount += requestRecord.assignments.filter(
            (assignment) => assignment.status === "ACTIVE",
          ).length;

          if (
            summary.latestRequest === null ||
            new Date(requestRecord.created_at).getTime() > new Date(summary.latestRequest.created_at).getTime()
          ) {
            summary.latestRequest = requestRecord;
          }

          accumulator[requestRecord.ward] = summary;
          return accumulator;
        },
        {},
      );

      return {
        chvs: chvResponse,
        latestRisks: wardResponse.latestRisks,
        alerts: alertResponse.results,
        wardMap,
        coverageRequests,
        coverageByWard,
        offlineMonitoring,
      };
    },
    enabled,
  });
}
