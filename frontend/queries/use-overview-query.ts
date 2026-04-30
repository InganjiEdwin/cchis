"use client";

import { useQuery } from "@tanstack/react-query";

import {
  fetchOverviewDataViaBff,
  type AlertRecord,
  type OverviewDecisionSummary,
  type OverviewFacilityReadinessSummary,
  type OverviewFreshnessSummary,
  type OverviewMapGuidance,
  type OverviewMissionMetrics,
  type OverviewSimulationReadiness,
  type OverviewTemporalMetrics,
  type OverviewTriggerLinkageSummary,
  type OverviewTriggerEvent,
  type LatestWardRisk,
  type OverviewStateModel,
  type WardMapResponse,
  type WardSummary,
} from "@/lib/dashboard";
import { getLatestTimestamp } from "@/lib/freshness";
import { queryKeys } from "@/lib/query-keys";

export type OverviewViewModel = {
  wards: WardSummary[];
  totalWards: number;
  highRiskWards: LatestWardRisk[];
  mediumRiskWards: LatestWardRisk[];
  recentAlerts: AlertRecord[];
  wardMap: WardMapResponse | null;
  alertsTodayCount: number;
  deliveredAlertRate: number;
  latestTimestamp: string | null;
  primaryCountyLabel: string;
  overviewState: OverviewStateModel;
  decisionSummary: OverviewDecisionSummary;
  triggerReviewQueue: OverviewTriggerEvent[];
  freshness: OverviewFreshnessSummary;
  temporalMetrics: OverviewTemporalMetrics;
  missionMetrics: OverviewMissionMetrics;
  mapGuidance: OverviewMapGuidance;
  triggerLinkage: OverviewTriggerLinkageSummary;
  facilityReadiness: OverviewFacilityReadinessSummary;
  simulationReadiness: OverviewSimulationReadiness;
};

function getOperationalAlertStatusRank(status: AlertRecord["status"]) {
  if (status === "RETRY_PENDING") return 0;
  if (status === "FAILED") return 1;
  if (status === "QUEUED") return 2;
  return 3;
}

function startOfTodayIso() {
  const date = new Date();
  date.setHours(0, 0, 0, 0);
  return date.getTime();
}

function buildOverviewViewModel(
  wards: WardSummary[],
  latestRisks: LatestWardRisk[],
  alerts: AlertRecord[],
  wardMap: WardMapResponse | null,
  overviewState: OverviewStateModel,
  decisionSummary: OverviewDecisionSummary,
  triggerReviewQueue: OverviewTriggerEvent[],
  freshness: OverviewFreshnessSummary,
  temporalMetrics: OverviewTemporalMetrics,
  missionMetrics: OverviewMissionMetrics,
  mapGuidance: OverviewMapGuidance,
  triggerLinkage: OverviewTriggerLinkageSummary,
  facilityReadiness: OverviewFacilityReadinessSummary,
  simulationReadiness: OverviewSimulationReadiness,
): OverviewViewModel {
  const highRiskWards = latestRisks
    .filter((item) => item.risk_level === "HIGH")
    .sort((left, right) => (right.risk_score ?? 0) - (left.risk_score ?? 0));
  const mediumRiskWards = latestRisks
    .filter((item) => item.risk_level === "MEDIUM")
    .sort((left, right) => (right.risk_score ?? 0) - (left.risk_score ?? 0));
  const latestTimestamp = getLatestTimestamp([
    ...latestRisks.map((item) => item.generated_at),
    ...alerts.map((item) => item.created_at),
  ]);
  const deliveredAlertRate = alerts.length
    ? Math.round((alerts.filter((item) => item.status === "DELIVERED").length / alerts.length) * 100)
    : 0;
  const alertsTodayCount = alerts.filter((item) => new Date(item.created_at).getTime() >= startOfTodayIso()).length;
  const countyCounts = wards.reduce<Map<string, number>>((accumulator, ward) => {
    accumulator.set(ward.county, (accumulator.get(ward.county) ?? 0) + 1);
    return accumulator;
  }, new Map<string, number>());
  const primaryCountyLabel =
    [...countyCounts.entries()].sort((left, right) => right[1] - left[1])[0]?.[0] ?? "Operational";
  const prioritizedRecentAlerts = [...alerts].sort((left, right) => {
    const statusDiff = getOperationalAlertStatusRank(left.status) - getOperationalAlertStatusRank(right.status);
    if (statusDiff !== 0) {
      return statusDiff;
    }

    return new Date(right.created_at).getTime() - new Date(left.created_at).getTime();
  });

  return {
    wards,
    totalWards: wards.length ? Math.max(wards.length, latestRisks.length) : latestRisks.length,
    highRiskWards,
    mediumRiskWards,
    recentAlerts: prioritizedRecentAlerts.slice(0, 10),
    wardMap,
    alertsTodayCount,
    deliveredAlertRate,
    latestTimestamp,
    primaryCountyLabel: primaryCountyLabel === "Operational" ? "Migori" : primaryCountyLabel,
    overviewState,
    decisionSummary,
    triggerReviewQueue,
    freshness,
    temporalMetrics,
    missionMetrics,
    mapGuidance,
    triggerLinkage,
    facilityReadiness,
    simulationReadiness,
  };
}

export function useOverviewQuery({ enabled = true }: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: queryKeys.overview.root(),
    queryFn: async (): Promise<OverviewViewModel> => {
      const data = await fetchOverviewDataViaBff();
      const migoriWards = data.wards.results.filter((ward) => ward.county === "Migori");
      const migoriWardIds = new Set(migoriWards.map((ward) => ward.id));
      const migoriRisks = data.latestRisks.filter((risk) => migoriWardIds.has(risk.ward_id));
      const migoriAlerts = data.alerts.results.filter((alert) => migoriWardIds.has(alert.ward));
      const model = buildOverviewViewModel(
        migoriWards,
        migoriRisks,
        migoriAlerts,
        data.wardMap ?? null,
        data.overviewState,
        data.decisionSummary,
        data.triggerReviewQueue,
        data.freshness,
        data.temporalMetrics,
        data.missionMetrics,
        data.mapGuidance,
        data.triggerLinkage,
        data.facilityReadiness,
        data.simulationReadiness,
      );

      return {
        ...model,
        totalWards: migoriWards.length,
      };
    },
    enabled,
  });
}
