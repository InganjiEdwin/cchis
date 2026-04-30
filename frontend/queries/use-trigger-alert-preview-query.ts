"use client";

import { useQuery } from "@tanstack/react-query";

import { fetchTriggerAlertPreviewViaBff, type TriggerActionType } from "@/lib/dashboard";
import { queryKeys } from "@/lib/query-keys";

export function useTriggerAlertPreviewQuery(
  wardId: number | null,
  triggerType: TriggerActionType | null,
  messageOverride: string | null = null,
  enabled = true,
) {
  return useQuery({
    queryKey: queryKeys.alerts.trigger.preview(wardId ?? "none", triggerType ?? "none", messageOverride),
    queryFn: async () =>
      fetchTriggerAlertPreviewViaBff({
        ward_id: wardId as number,
        trigger_type: triggerType as TriggerActionType,
        ...(messageOverride ? { message_override: messageOverride } : {}),
      }),
    enabled: Boolean(wardId && triggerType) && enabled,
  });
}
