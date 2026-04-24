"use client";

import { useQuery } from "@tanstack/react-query";

import {
  fetchOverviewDataViaBff,
  type AlertRecord,
  type LatestWardRisk,
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
  alertsTodayCount: number;
  deliveredAlertRate: number;
  latestTimestamp: string | null;
  primaryCountyLabel: string;
};

function startOfTodayIso() {
  const date = new Date();
  date.setHours(0, 0, 0, 0);
  return date.getTime();
}

function buildOverviewViewModel(
  wards: WardSummary[],
  latestRisks: LatestWardRisk[],
  alerts: AlertRecord[],
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

  return {
    wards,
    totalWards: wards.length ? Math.max(wards.length, latestRisks.length) : latestRisks.length,
    highRiskWards,
    mediumRiskWards,
    recentAlerts: alerts.slice(0, 5),
    alertsTodayCount,
    deliveredAlertRate,
    latestTimestamp,
    primaryCountyLabel: primaryCountyLabel === "Operational" ? "Migori" : primaryCountyLabel,
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
      const model = buildOverviewViewModel(migoriWards, migoriRisks, migoriAlerts);

      return {
        ...model,
        totalWards: migoriWards.length,
      };
    },
    enabled,
  });
}
