"use client";

import { useQuery } from "@tanstack/react-query";

import { fetchWardRiskDataViaBff, type WardDecisionConsoleTriggerState, type WardQueueSummary, type WardQueueUrgency } from "@/lib/dashboard";
import { queryKeys } from "@/lib/query-keys";

export type WardListItem = {
  id: number;
  publicId: string;
  name: string;
  county: string;
  subCounty: string;
  riskLevel: "LOW" | "MEDIUM" | "HIGH" | "UNKNOWN";
  riskScore: number | null;
  updatedAt: string | null;
  predictedCases: number | null;
  recentAlertCount: number;
  triggerState: WardDecisionConsoleTriggerState;
  requiresAction: boolean;
  deliveryConcernCount: number;
  workflowPublicId: string | null;
  recommendedAction: string | null;
};

type UseWardsQueryParams = {
  county?: string;
  q?: string;
  risk?: string;
  sub_county?: string;
  ordering?: string;
  enabled?: boolean;
};

export function useWardsQuery({
  county,
  q,
  risk,
  sub_county,
  ordering,
  enabled = true,
}: UseWardsQueryParams) {
  return useQuery({
    queryKey: queryKeys.wards.list({
      county,
      q: q ?? "",
      risk: risk ?? "",
      sub_county: sub_county ?? "",
      ordering: ordering ?? "",
    }),
    queryFn: async () => {
      const data = await fetchWardRiskDataViaBff({
        county,
        q,
        risk,
        sub_county,
        ordering,
      });

      const visibleWards = county
        ? data.wards.results.filter((ward) => ward.county === county)
        : data.wards.results;
      const latestRiskByWardId = new Map(data.latestRisks.map((riskItem) => [riskItem.ward_id, riskItem]));
      const queueItemByWardId = new Map(data.wardQueue.items.map((item) => [item.id, item]));

      const items = visibleWards.map<WardListItem>((ward) => {
        const queueItem = queueItemByWardId.get(ward.id);
        const riskItem = latestRiskByWardId.get(ward.id);

        return {
          id: ward.id,
          publicId: ward.public_id,
          name: ward.name,
          county: ward.county,
          subCounty: ward.sub_county,
          riskLevel: queueItem?.risk_level ?? riskItem?.risk_level ?? ward.current_risk_level ?? "UNKNOWN",
          riskScore: queueItem?.risk_score ?? riskItem?.risk_score ?? ward.current_risk_score ?? null,
          updatedAt: queueItem?.last_updated_at ?? riskItem?.generated_at ?? ward.updated_at ?? null,
          predictedCases: queueItem?.expected_cases_7d ?? riskItem?.predicted_cases ?? null,
          recentAlertCount: queueItem?.recent_alert_count ?? data.recentAlertCountsByWard[String(ward.id)] ?? 0,
          triggerState: queueItem?.trigger_state ?? "NONE",
          requiresAction: queueItem?.requires_action ?? false,
          deliveryConcernCount: queueItem?.delivery_concern_count ?? 0,
          workflowPublicId: queueItem?.workflow_public_id ?? null,
          recommendedAction: queueItem?.recommended_action ?? null,
        };
      });

      return {
        items,
        wards: data.wards,
        latestRisks: data.latestRisks,
        wardQueueSummary: data.wardQueue.summary as WardQueueSummary,
        wardQueueUrgency: data.wardQueue.urgency as WardQueueUrgency,
      };
    },
    enabled,
  });
}
