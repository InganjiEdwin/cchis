"use client";

import { useQuery } from "@tanstack/react-query";

import { fetchWardRiskDataViaBff } from "@/lib/dashboard";
import { queryKeys } from "@/lib/query-keys";

export type WardListItem = {
  id: number;
  name: string;
  county: string;
  subCounty: string;
  riskLevel: "LOW" | "MEDIUM" | "HIGH" | "UNKNOWN";
  riskScore: number | null;
  updatedAt: string | null;
  predictedCases: number;
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

      const items = visibleWards.map<WardListItem>((ward) => {
        const riskItem = latestRiskByWardId.get(ward.id);

        return {
          id: ward.id,
          name: ward.name,
          county: ward.county,
          subCounty: ward.sub_county,
          riskLevel: riskItem?.risk_level ?? ward.current_risk_level ?? "UNKNOWN",
          riskScore: riskItem?.risk_score ?? ward.current_risk_score ?? null,
          updatedAt: riskItem?.generated_at ?? ward.updated_at ?? null,
          predictedCases: riskItem?.predicted_cases ?? 0,
        };
      });

      return {
        items,
        wards: data.wards,
        latestRisks: data.latestRisks,
      };
    },
    enabled,
  });
}
