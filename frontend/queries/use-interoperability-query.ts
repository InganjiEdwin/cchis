"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  createInteroperabilityOrgUnitMappingImportViaBff,
  createInteroperabilityRiskScoreExportPreviewViaBff,
  fetchInteroperabilityDashboardViaBff,
  fetchInteroperabilityRunViaBff,
  retryInteroperabilityRunViaBff,
  type InteroperabilityOrgUnitMappingImportPayload,
} from "@/lib/dashboard";
import { queryKeys } from "@/lib/query-keys";

export function useInteroperabilityDashboardQuery() {
  return useQuery({
    queryKey: queryKeys.interoperability.dashboard(),
    queryFn: fetchInteroperabilityDashboardViaBff,
  });
}

export function useInteroperabilityRunDetailMutation() {
  return useMutation({
    mutationFn: (publicId: string) => fetchInteroperabilityRunViaBff(publicId),
  });
}

export function useInteroperabilityOrgUnitMappingImportMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: InteroperabilityOrgUnitMappingImportPayload) =>
      createInteroperabilityOrgUnitMappingImportViaBff(payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.interoperability.root() });
    },
  });
}

export function useInteroperabilityExportPreviewMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: { system_key?: string; mapping_version_label?: string }) =>
      createInteroperabilityRiskScoreExportPreviewViaBff(payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.interoperability.root() });
    },
  });
}

export function useInteroperabilityRetryMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (publicId: string) => retryInteroperabilityRunViaBff(publicId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.interoperability.root() });
    },
  });
}
