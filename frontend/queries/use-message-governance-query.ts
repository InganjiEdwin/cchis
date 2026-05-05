"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  approveMessageTemplateViaBff,
  approveUssdMenuVersionViaBff,
  fetchMessageGovernanceDashboardViaBff,
  fetchMessageTemplateDetailViaBff,
  type FetchMessageGovernanceParams,
  type MessageTemplateApprovalPayload,
  type UssdMenuVersionApprovalPayload,
} from "@/lib/dashboard";
import { queryKeys } from "@/lib/query-keys";

export function useMessageGovernanceDashboardQuery(filters: FetchMessageGovernanceParams = {}) {
  return useQuery({
    queryKey: queryKeys.messageGovernance.dashboard(filters),
    queryFn: () => fetchMessageGovernanceDashboardViaBff(filters),
  });
}

export function useMessageTemplateDetailQuery(publicId: string | null) {
  return useQuery({
    queryKey: queryKeys.messageGovernance.template(publicId ?? ""),
    queryFn: () => fetchMessageTemplateDetailViaBff(publicId as string),
    enabled: Boolean(publicId),
  });
}

export function useApproveMessageTemplateMutation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      publicId,
      payload,
    }: {
      publicId: string;
      payload: MessageTemplateApprovalPayload;
    }) => approveMessageTemplateViaBff(publicId, payload),
    onSuccess: async (detail) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.messageGovernance.root() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.messageGovernance.template(detail.template.public_id) }),
      ]);
    },
  });
}

export function useApproveUssdMenuVersionMutation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      publicId,
      payload,
    }: {
      publicId: string;
      payload: UssdMenuVersionApprovalPayload;
    }) => approveUssdMenuVersionViaBff(publicId, payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.messageGovernance.root() });
    },
  });
}
