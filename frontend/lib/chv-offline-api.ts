import type { CurrentUser } from "@/lib/auth";
import type {
  ChvOfflineDownloadBundleInput,
  ChvOfflineLocalStore,
  ChvOfflineUploadType,
  ChvPendingSyncItem,
} from "@/lib/chv-offline-store";

export const CHV_OFFLINE_CONTRACT_VERSION = "chv-offline-v1";
export const CHV_OFFLINE_DEVICE_ID_KEY = "cchis.chv_offline.device_id";
export const CHV_OFFLINE_DEVICE_REGISTRATION_ID_KEY = "cchis.chv_offline.device_registration_id";

const SYNCABLE_UPLOAD_TYPES: ChvOfflineUploadType[] = [
  "symptom_triage",
  "suspected_case_signal",
  "prevention_visit",
  "task_ack",
  "alert_ack",
];
const SYMPTOM_UPLOAD_FIELDS = ["diarrhea", "vomiting", "dehydration", "fever", "text_input"] as const;
const PREVENTION_VISIT_UPLOAD_FIELDS = [
  "task_public_id",
  "action_public_id",
  "visit_completed",
  "households_reached_count",
  "messages_delivered_count",
  "water_treatment_demo",
  "soap_or_handwashing_discussed",
] as const;
const TASK_ACK_UPLOAD_FIELDS = [
  "task_public_id",
  "action_public_id",
  "assignment_public_id",
  "acknowledgment_status",
  "coded_reason",
] as const;
const ALERT_ACK_UPLOAD_FIELDS = [
  "alert_public_id",
  "task_public_id",
  "action_public_id",
  "acknowledgment_status",
  "coded_reason",
] as const;

export type ChvOfflineSyncUploadRequest = {
  client_submission_id: string;
  idempotency_key: string;
  payload_version: "chv-upload-payload-v1";
  upload_type: ChvOfflineUploadType;
  download_bundle_version?: string;
  payload: Record<string, unknown>;
};

export type ChvOfflineSyncRequest = {
  contract_version: typeof CHV_OFFLINE_CONTRACT_VERSION;
  source_device_id: string;
  device_registration_id?: string;
  ward_id: number;
  session_scope: {
    ward_id: number;
    scope_key: string;
  };
  download_bundle_version: string;
  uploads: ChvOfflineSyncUploadRequest[];
};

export type ChvOfflineSyncResult = {
  client_submission_id: string;
  idempotency_key: string;
  upload_type: ChvOfflineUploadType;
  sync_status: string;
  conflict_state: string;
  replayed: boolean;
  server_receipt: Record<string, unknown>;
};

export type ChvOfflineSyncResponse = {
  message: string;
  contract_version: string;
  processed_count: number;
  sync_health_record: {
    last_successful_sync_at: string | null;
    pending_upload_count: number;
    failed_upload_count: number;
    sync_health: "ONLINE" | "DELAYED" | "OFFLINE";
  };
  results: ChvOfflineSyncResult[];
};

export type ChvOfflineContractResponse = {
  contract_version: string;
  session_scope: {
    ward_id: number;
    scope_key: string;
  };
  download_bundle: ChvOfflineDownloadBundleInput;
  sync_health_record: ChvOfflineSyncResponse["sync_health_record"];
};

export type ChvOfflineDeviceRegistrationResponse = {
  public_id: string;
  device_id: string;
  contract_version: string;
  download_bundle_version: string;
  session_scope: {
    ward_id: number;
    scope_key: string;
  };
  sync_health_record: ChvOfflineSyncResponse["sync_health_record"];
};

export class ChvOfflineApiError extends Error {
  status: number | null;

  constructor(message: string, status: number | null = null) {
    super(message);
    this.status = status;
  }
}

function storageOrNull(storage?: Storage) {
  if (storage) {
    return storage;
  }
  if (typeof window === "undefined") {
    return null;
  }
  return window.localStorage;
}

function createBrowserDeviceId() {
  const cryptoObject = typeof crypto !== "undefined" ? crypto : null;
  if (cryptoObject && "randomUUID" in cryptoObject) {
    return `web-${cryptoObject.randomUUID()}`;
  }
  return `web-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export function getOrCreateChvOfflineDeviceId(storage?: Storage) {
  const targetStorage = storageOrNull(storage);
  if (!targetStorage) {
    return createBrowserDeviceId();
  }

  const existing = targetStorage.getItem(CHV_OFFLINE_DEVICE_ID_KEY);
  if (existing) {
    return existing;
  }

  const deviceId = createBrowserDeviceId();
  targetStorage.setItem(CHV_OFFLINE_DEVICE_ID_KEY, deviceId);
  return deviceId;
}

export function getStoredChvOfflineDeviceRegistrationId(storage?: Storage) {
  return storageOrNull(storage)?.getItem(CHV_OFFLINE_DEVICE_REGISTRATION_ID_KEY) ?? "";
}

export function storeChvOfflineDeviceRegistrationId(registrationId: string, storage?: Storage) {
  const targetStorage = storageOrNull(storage);
  if (targetStorage && registrationId) {
    targetStorage.setItem(CHV_OFFLINE_DEVICE_REGISTRATION_ID_KEY, registrationId);
  }
  return registrationId;
}

export function isChvOfflineUploadSyncable(uploadType: ChvOfflineUploadType) {
  return SYNCABLE_UPLOAD_TYPES.includes(uploadType);
}

export function sanitizeChvOfflineUploadPayload(
  uploadType: ChvOfflineUploadType,
  payload: Record<string, unknown>,
) {
  const allowedFields =
    uploadType === "prevention_visit"
      ? PREVENTION_VISIT_UPLOAD_FIELDS
      : uploadType === "task_ack"
        ? TASK_ACK_UPLOAD_FIELDS
        : uploadType === "alert_ack"
          ? ALERT_ACK_UPLOAD_FIELDS
          : SYMPTOM_UPLOAD_FIELDS;

  return allowedFields.reduce<Record<string, unknown>>((sanitized, field) => {
    if (field in payload) {
      sanitized[field] = payload[field];
    }
    return sanitized;
  }, {});
}

export function buildChvOfflineSyncRequest(
  store: ChvOfflineLocalStore,
  user: CurrentUser,
  pendingItems: ChvPendingSyncItem[],
  sourceDeviceId: string,
  deviceRegistrationId = "",
): ChvOfflineSyncRequest {
  if (typeof user.ward !== "number") {
    throw new ChvOfflineApiError("An assigned ward is required before syncing.");
  }

  return {
    contract_version: CHV_OFFLINE_CONTRACT_VERSION,
    source_device_id: sourceDeviceId,
    ...(deviceRegistrationId ? { device_registration_id: deviceRegistrationId } : {}),
    ward_id: user.ward,
    session_scope: {
      ward_id: user.ward,
      scope_key: store.scopeKey,
    },
    download_bundle_version: store.bundleMetadata?.downloadBundleVersion ?? "",
    uploads: pendingItems.map((item) => ({
      client_submission_id: item.clientSubmissionId,
      idempotency_key: item.idempotencyKey,
      payload_version: "chv-upload-payload-v1",
      upload_type: item.uploadType,
      download_bundle_version: item.downloadBundleVersion,
      payload: sanitizeChvOfflineUploadPayload(item.uploadType, item.payload),
    })),
  };
}

export async function fetchChvOfflineContractViaBff() {
  const response = await fetch("/api/chv/offline/contract", {
    method: "GET",
    credentials: "include",
  });

  if (!response.ok) {
    throw new ChvOfflineApiError(await readErrorDetail(response), response.status);
  }

  return (await response.json()) as ChvOfflineContractResponse;
}

export async function postChvDeviceRegistrationViaBff(payload: {
  device_id: string;
  contract_version?: string;
  app_version?: string;
  platform?: "ANDROID" | "IOS" | "WEB" | "UNKNOWN";
}) {
  const response = await fetch("/api/chv/device-registrations", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    credentials: "include",
    body: JSON.stringify({
      contract_version: CHV_OFFLINE_CONTRACT_VERSION,
      platform: "WEB",
      ...payload,
    }),
  });

  if (!response.ok) {
    throw new ChvOfflineApiError(await readErrorDetail(response), response.status);
  }

  return (await response.json()) as ChvOfflineDeviceRegistrationResponse;
}

async function readErrorDetail(response: Response) {
  try {
    const body = (await response.json()) as Record<string, unknown>;
    if (typeof body.detail === "string") {
      return body.detail;
    }
    if (typeof body.message === "string") {
      return body.message;
    }
  } catch {
    // Keep the generic message below.
  }

  return "Unable to sync offline work.";
}

export async function postChvOfflineSyncViaBff(request: ChvOfflineSyncRequest) {
  const response = await fetch("/api/chv/sync", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    credentials: "include",
    body: JSON.stringify(request),
  });

  if (!response.ok) {
    throw new ChvOfflineApiError(await readErrorDetail(response), response.status);
  }

  return (await response.json()) as ChvOfflineSyncResponse;
}
