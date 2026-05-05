"use client";

import { useQuery } from "@tanstack/react-query";

import {
  fetchSourceDataFeedTypesViaBff,
  fetchSourceDataFreshnessViaBff,
  fetchSourceDataOperationsViaBff,
  fetchSourceDataOverviewViaBff,
  fetchSourceDataUploadViaBff,
  fetchSourceDataUploadsViaBff,
  type SourceDataUploadFilters,
  type SourceDataUploadBatchRecord,
} from "@/lib/dashboard";
import { queryKeys } from "@/lib/query-keys";

export function useSourceDataFeedTypesQuery() {
  return useQuery({
    queryKey: queryKeys.sourceData.feedTypes(),
    queryFn: fetchSourceDataFeedTypesViaBff,
  });
}

export function useSourceDataOverviewQuery() {
  return useQuery({
    queryKey: [...queryKeys.sourceData.root(), "overview"] as const,
    queryFn: fetchSourceDataOverviewViaBff,
  });
}

export function useSourceDataFreshnessQuery() {
  return useQuery({
    queryKey: [...queryKeys.sourceData.root(), "freshness"] as const,
    queryFn: fetchSourceDataFreshnessViaBff,
  });
}

export function useSourceDataOperationsQuery() {
  return useQuery({
    queryKey: [...queryKeys.sourceData.root(), "operations"] as const,
    queryFn: fetchSourceDataOperationsViaBff,
    refetchInterval: 30000,
  });
}

export function useSourceDataUploadsQuery(filters: SourceDataUploadFilters = {}) {
  return useQuery({
    queryKey: queryKeys.sourceData.uploads(filters),
    queryFn: () => fetchSourceDataUploadsViaBff(filters),
  });
}

export function useSourceDataUploadQuery(publicId: string | null) {
  return useQuery({
    queryKey: queryKeys.sourceData.upload(publicId ?? "none"),
    queryFn: () => fetchSourceDataUploadViaBff(publicId as string),
    enabled: Boolean(publicId),
    refetchInterval: (query) => {
      const upload = query.state.data as SourceDataUploadBatchRecord | undefined;
      return upload?.validation_status === "running"
        || upload?.import_status === "running"
        || upload?.status === "validating"
        || upload?.status === "confirming"
        ? 2500
        : false;
    },
  });
}
