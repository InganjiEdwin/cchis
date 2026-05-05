"use client";

import { useQuery } from "@tanstack/react-query";

import {
  fetchSourceDataFeedTypesViaBff,
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
      return upload?.validation_status === "running" || upload?.status === "validating" ? 2500 : false;
    },
  });
}
