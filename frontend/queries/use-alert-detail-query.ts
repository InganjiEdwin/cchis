"use client";

import { useQuery } from "@tanstack/react-query";

import { fetchAlertByIdViaBff, type AlertIntelligenceCapabilities, type AlertIntelligenceClassification, type AlertIntelligenceDelivery, type AlertIntelligenceFreshness, type AlertIntelligenceRiskContext, type AlertIntelligenceStateItem, type AlertIntelligenceTimelineEntry, type AlertRecord, type WardDetailSummary } from "@/lib/dashboard";
import { queryKeys } from "@/lib/query-keys";

type AlertDetailData = {
  alert: AlertRecord | null;
  ward_detail: WardDetailSummary | null;
  classification: AlertIntelligenceClassification;
  risk_context: AlertIntelligenceRiskContext;
  delivery: AlertIntelligenceDelivery;
  current_state: AlertIntelligenceStateItem[];
  freshness: AlertIntelligenceFreshness;
  timeline: AlertIntelligenceTimelineEntry[];
  capabilities: AlertIntelligenceCapabilities;
};

type UseAlertDetailQueryParams = {
  alertId: number;
  enabled?: boolean;
};

export function useAlertDetailQuery({ alertId, enabled = true }: UseAlertDetailQueryParams) {
  return useQuery({
    queryKey: queryKeys.alerts.detail(alertId),
    queryFn: async (): Promise<AlertDetailData> => {
      return fetchAlertByIdViaBff(alertId);
    },
    enabled,
  });
}
