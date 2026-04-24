"use client";

import { useQuery } from "@tanstack/react-query";

import { fetchSystemDataViaBff } from "@/lib/dashboard";
import { queryKeys } from "@/lib/query-keys";

export type SystemSnapshot = {
  visibleWards: number;
  visibleAlerts: number;
  visibleFacilities: number;
  highRiskWards: number;
  wardsWithFreshRisk: number;
  latestRiskTimestamp: string | null;
  latestAlertTimestamp: string | null;
  latestFacilityTimestamp: string | null;
  latestChvTimestamp: string | null;
  queuedAlerts: number;
  retryPendingAlerts: number;
  failedAlerts: number;
  deliveredAlerts: number;
  latestFailedAlertTimestamp: string | null;
  latestRetryAlertTimestamp: string | null;
  latestDeliveredAlertTimestamp: string | null;
  activeChvs: number;
  onlineChvs: number;
  delayedChvs: number;
  offlineChvs: number;
  triageSessions24h: number;
  referrals24h: number;
  syncPayloads24h: number;
  ussdSessions24h: number;
  deliveryBackends: Array<{ name: string; count: number }>;
};

function latestTimestamp(values: Array<string | null | undefined>) {
  return values.reduce<string | null>((latest, value) => {
    if (!value) {
      return latest;
    }

    if (!latest || new Date(value).getTime() > new Date(latest).getTime()) {
      return value;
    }

    return latest;
  }, null);
}

export function useSystemQuery({ enabled = true }: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: queryKeys.system.root(),
    queryFn: async (): Promise<SystemSnapshot> => {
      const data = await fetchSystemDataViaBff();

      const highRiskWards = data.latestRisks.filter((item) => item.risk_level === "HIGH").length;
      const wardsWithFreshRisk = data.latestRisks.filter((item) => item.generated_at).length;
      const latestRiskTimestamp = latestTimestamp(data.latestRisks.map((item) => item.generated_at));
      const latestAlertTimestamp = latestTimestamp(data.alerts.results.map((item) => item.created_at));
      const latestFacilityTimestamp = data.facilities.results[0]?.updated_at ?? null;
      const latestChvTimestamp = latestTimestamp(
        data.chvOperations.flatMap((item) => [item.last_activity_at, item.last_sync_at]),
      );

      const deliveryBackends = Array.from(
        data.alerts.results.reduce((accumulator, alert) => {
          const name = alert.delivery_backend || "unassigned-backend";
          accumulator.set(name, (accumulator.get(name) ?? 0) + 1);
          return accumulator;
        }, new Map<string, number>()),
      )
        .map(([name, count]) => ({ name, count }))
        .sort((left, right) => right.count - left.count);

      const activeChvs = data.chvOperations.filter((item) => item.is_active).length;
      const onlineChvs = data.chvOperations.filter((item) => item.sync_health === "ONLINE").length;
      const delayedChvs = data.chvOperations.filter((item) => item.sync_health === "DELAYED").length;
      const offlineChvs = data.chvOperations.filter((item) => item.sync_health === "OFFLINE").length;

      return {
        visibleWards: data.wards.count,
        visibleAlerts: data.alerts.count,
        visibleFacilities: data.facilities.count,
        highRiskWards,
        wardsWithFreshRisk,
        latestRiskTimestamp,
        latestAlertTimestamp,
        latestFacilityTimestamp,
        latestChvTimestamp,
        queuedAlerts: data.queuedAlerts.count,
        retryPendingAlerts: data.retryAlerts.count,
        failedAlerts: data.failedAlerts.count,
        deliveredAlerts: data.deliveredAlerts.count,
        latestFailedAlertTimestamp: data.failedAlerts.results[0]?.created_at ?? null,
        latestRetryAlertTimestamp: data.retryAlerts.results[0]?.created_at ?? null,
        latestDeliveredAlertTimestamp: data.deliveredAlerts.results[0]?.created_at ?? null,
        activeChvs,
        onlineChvs,
        delayedChvs,
        offlineChvs,
        triageSessions24h: data.chvOperations.reduce((sum, item) => sum + item.triage_sessions_24h, 0),
        referrals24h: data.chvOperations.reduce((sum, item) => sum + item.referrals_24h, 0),
        syncPayloads24h: data.chvOperations.reduce((sum, item) => sum + item.sync_payloads_24h, 0),
        ussdSessions24h: data.chvOperations.reduce((sum, item) => sum + item.ussd_sessions_24h, 0),
        deliveryBackends,
      };
    },
    enabled,
  });
}
