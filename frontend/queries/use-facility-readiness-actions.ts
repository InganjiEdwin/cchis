"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import {
  acknowledgeFacilityReadinessReviewViaBff,
  createFacilityEscalationViaBff,
  createFacilityReadinessReviewViaBff,
  createFacilityUpdateRequestViaBff,
  type AcknowledgeFacilityReadinessReviewPayload,
  type CreateFacilityEscalationPayload,
  type CreateFacilityReadinessReviewPayload,
  type CreateFacilityUpdateRequestPayload,
} from "@/lib/dashboard";
import { queryKeys } from "@/lib/query-keys";

function useInvalidateFacilityReadiness(facilityId: number | null) {
  const queryClient = useQueryClient();

  return async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: queryKeys.facilityReadiness.root() }),
      facilityId
        ? queryClient.invalidateQueries({ queryKey: queryKeys.facilityReadiness.detail(facilityId) })
        : Promise.resolve(),
      queryClient.invalidateQueries({ queryKey: queryKeys.system.root() }),
    ]);
  };
}

export function useCreateFacilityReadinessReviewMutation(facilityId: number | null) {
  const invalidate = useInvalidateFacilityReadiness(facilityId);

  return useMutation({
    mutationFn: async (payload: CreateFacilityReadinessReviewPayload = {}) => {
      if (!facilityId) {
        throw new Error("A facility must be selected before opening a review.");
      }
      return createFacilityReadinessReviewViaBff(facilityId, payload);
    },
    onSuccess: invalidate,
  });
}

export function useAcknowledgeFacilityReadinessReviewMutation(facilityId: number | null) {
  const invalidate = useInvalidateFacilityReadiness(facilityId);

  return useMutation({
    mutationFn: async ({
      reviewPublicId,
      payload,
    }: {
      reviewPublicId: string;
      payload?: AcknowledgeFacilityReadinessReviewPayload;
    }) => acknowledgeFacilityReadinessReviewViaBff(reviewPublicId, payload ?? {}),
    onSuccess: invalidate,
  });
}

export function useCreateFacilityUpdateRequestMutation(facilityId: number | null) {
  const invalidate = useInvalidateFacilityReadiness(facilityId);

  return useMutation({
    mutationFn: async ({
      reviewPublicId,
      payload,
    }: {
      reviewPublicId: string;
      payload?: CreateFacilityUpdateRequestPayload;
    }) => createFacilityUpdateRequestViaBff(reviewPublicId, payload ?? {}),
    onSuccess: invalidate,
  });
}

export function useCreateFacilityEscalationMutation(facilityId: number | null) {
  const invalidate = useInvalidateFacilityReadiness(facilityId);

  return useMutation({
    mutationFn: async ({
      reviewPublicId,
      payload,
    }: {
      reviewPublicId: string;
      payload?: CreateFacilityEscalationPayload;
    }) => createFacilityEscalationViaBff(reviewPublicId, payload ?? {}),
    onSuccess: invalidate,
  });
}
