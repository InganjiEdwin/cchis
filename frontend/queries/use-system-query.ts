"use client";

import { useQuery } from "@tanstack/react-query";

import { fetchSystemDataViaBff, type SystemControlStatus } from "@/lib/dashboard";
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
  controlStatus: SystemControlStatus;
};

export function useSystemQuery({ enabled = true }: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: queryKeys.system.root(),
    queryFn: async (): Promise<SystemSnapshot> => {
      const data = await fetchSystemDataViaBff();
      const readiness = data.readiness;

      return {
        visibleWards: readiness.visible_wards,
        visibleAlerts: readiness.visible_alerts,
        visibleFacilities: readiness.visible_facilities,
        highRiskWards: readiness.high_risk_wards,
        wardsWithFreshRisk: readiness.wards_with_fresh_risk,
        latestRiskTimestamp: readiness.latest_risk_timestamp,
        latestAlertTimestamp: readiness.latest_alert_timestamp,
        latestFacilityTimestamp: readiness.latest_facility_timestamp,
        latestChvTimestamp: readiness.latest_chv_timestamp,
        queuedAlerts: readiness.queued_alerts,
        retryPendingAlerts: readiness.retry_pending_alerts,
        failedAlerts: readiness.failed_alerts,
        deliveredAlerts: readiness.delivered_alerts,
        latestFailedAlertTimestamp: readiness.latest_failed_alert_timestamp,
        latestRetryAlertTimestamp: readiness.latest_retry_alert_timestamp,
        latestDeliveredAlertTimestamp: readiness.latest_delivered_alert_timestamp,
        activeChvs: readiness.active_chvs,
        onlineChvs: readiness.online_chvs,
        delayedChvs: readiness.delayed_chvs,
        offlineChvs: readiness.offline_chvs,
        triageSessions24h: readiness.triage_sessions_24h,
        referrals24h: readiness.referrals_24h,
        syncPayloads24h: readiness.sync_payloads_24h,
        ussdSessions24h: readiness.ussd_sessions_24h,
        deliveryBackends: readiness.delivery_backends,
        controlStatus: data.controlStatus,
      };
    },
    enabled,
  });
}
