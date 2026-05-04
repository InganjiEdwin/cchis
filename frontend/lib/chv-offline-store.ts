const HOURS_TO_MS = 60 * 60 * 1000;
const DAYS_TO_MS = 24 * HOURS_TO_MS;

export const CHV_OFFLINE_LOCAL_SCHEMA_VERSION = 1;
export const CHV_OFFLINE_STORE_KEY_PREFIX = "cchis.chv_offline.local";

export const CHV_OFFLINE_RETENTION_RULES = {
  assignedTasksDays: 7,
  wardGuidanceHours: 24,
  symptomTriageDraftHours: 24,
  preventionVisitDraftHours: 72,
  pendingSyncItemDays: 14,
  failedSyncItemDays: 7,
  conflictItemDays: 7,
  lastSuccessfulSyncMetadataDays: 30,
} as const;

export type ChvOfflineUploadType =
  | "symptom_triage"
  | "suspected_case_signal"
  | "prevention_visit"
  | "task_ack"
  | "alert_ack";

export type ChvOfflineSyncStatus = "PENDING" | "SENDING" | "FAILED" | "SENT";
export type ChvOfflineConflictState =
  | "NONE"
  | "REPLAYED"
  | "SCOPE_MISMATCH"
  | "STALE_BUNDLE"
  | "UNSUPPORTED_UPLOAD";

type LocalEntityBase = {
  schemaVersion: typeof CHV_OFFLINE_LOCAL_SCHEMA_VERSION;
  localId: string;
  scopeKey: string;
  createdAt: string;
  updatedAt: string;
  expiresAt: string;
};

export type ChvOfflineBundleMetadata = {
  schemaVersion: typeof CHV_OFFLINE_LOCAL_SCHEMA_VERSION;
  contractVersion: string;
  downloadBundleVersion: string;
  taskBundleSchemaVersion: string;
  guidanceBundleSchemaVersion: string;
  ruleBundleVersion: string;
  generatedAt: string;
  cachedAt: string;
  expiresAt: string;
};

export type ChvOfflineAssignedTask = LocalEntityBase & {
  taskPublicId: string;
  taskType: string;
  actionType?: string;
  coverageRequestPublicId?: string;
  status: string;
  priority: string;
  wardId: number;
  wardPublicId: string;
  dueAt: string | null;
  startAt: string | null;
  endAt: string | null;
  allowedUploadTypes: ChvOfflineUploadType[];
  minimumCapture: string[];
  downloadBundleVersion: string;
};

export type ChvOfflineWardGuidance = LocalEntityBase & {
  guidancePublicId: string;
  templateKey: string;
  language: string;
  version: number;
  audienceType: string;
  title: string;
  body: string;
  publicHealthCaveats: string;
  downloadBundleVersion: string;
};

export type ChvSymptomTriageDraft = LocalEntityBase & {
  draftType: "symptom_triage";
  wardId: number;
  wardPublicId: string;
  diarrhea: boolean;
  vomiting: boolean;
  dehydration: boolean;
  fever: boolean;
  textInput: string;
};

export type ChvPreventionVisitDraft = LocalEntityBase & {
  draftType: "prevention_visit";
  taskPublicId: string;
  actionPublicId: string;
  visitCompleted: boolean;
  householdsReachedCount: number;
  messagesDeliveredCount: number;
  waterTreatmentDemo: boolean;
  soapOrHandwashingDiscussed: boolean;
};

export type ChvPendingSyncItem = LocalEntityBase & {
  clientSubmissionId: string;
  idempotencyKey: string;
  uploadType: ChvOfflineUploadType;
  status: Extract<ChvOfflineSyncStatus, "PENDING" | "SENDING">;
  payload: Record<string, unknown>;
  draftLocalId: string | null;
  downloadBundleVersion: string;
  attemptCount: number;
  lastAttemptAt: string | null;
};

export type ChvFailedSyncItem = LocalEntityBase & {
  clientSubmissionId: string;
  idempotencyKey: string;
  uploadType: ChvOfflineUploadType;
  payload: Record<string, unknown>;
  draftLocalId: string | null;
  downloadBundleVersion: string;
  attemptCount: number;
  failedAt: string;
  failureReason: string;
  serverStatus: number | null;
};

export type ChvConflictItem = LocalEntityBase & {
  clientSubmissionId: string;
  idempotencyKey: string;
  uploadType: ChvOfflineUploadType;
  conflictState: ChvOfflineConflictState;
  serverReceipt: Record<string, unknown>;
  resolutionStatus: "UNRESOLVED" | "RESOLVED" | "DISMISSED";
};

export type ChvLastSuccessfulSyncMetadata = {
  schemaVersion: typeof CHV_OFFLINE_LOCAL_SCHEMA_VERSION;
  scopeKey: string;
  contractVersion: string;
  deviceRegistrationId: string;
  sourceDeviceId: string;
  downloadBundleVersion: string;
  lastSuccessfulSyncAt: string;
  pendingUploadCount: number;
  failedUploadCount: number;
  syncHealth: "ONLINE" | "DELAYED" | "OFFLINE";
  expiresAt: string;
};

export type ChvOfflineLocalStore = {
  schemaVersion: typeof CHV_OFFLINE_LOCAL_SCHEMA_VERSION;
  scopeKey: string;
  createdAt: string;
  updatedAt: string;
  retentionRules: typeof CHV_OFFLINE_RETENTION_RULES;
  bundleMetadata: ChvOfflineBundleMetadata | null;
  assignedTasks: ChvOfflineAssignedTask[];
  wardGuidance: ChvOfflineWardGuidance[];
  symptomTriageDrafts: ChvSymptomTriageDraft[];
  preventionVisitDrafts: ChvPreventionVisitDraft[];
  pendingSyncItems: ChvPendingSyncItem[];
  failedSyncItems: ChvFailedSyncItem[];
  conflictItems: ChvConflictItem[];
  lastSuccessfulSync: ChvLastSuccessfulSyncMetadata | null;
};

export type ChvOfflineDownloadBundleInput = {
  version: string;
  generated_at: string;
  expires_at: string;
  task_bundle: {
    schema_version: string;
    tasks: Array<{
      task_public_id: string;
      task_type: string;
      action_type?: string;
      coverage_request_public_id?: string;
      status: string;
      priority: string;
      ward_id: number;
      ward_public_id: string;
      due_at?: string | null;
      start_at?: string | null;
      end_at?: string | null;
      allowed_upload_types?: ChvOfflineUploadType[];
      minimum_capture?: string[];
    }>;
  };
  guidance_bundle: {
    schema_version: string;
    items: Array<{
      guidance_public_id: string;
      template_key: string;
      language: string;
      version: number;
      audience_type: string;
      title: string;
      body: string;
      public_health_caveats?: string;
    }>;
  };
  decision_support_rule_bundle: {
    version: string;
  };
};

export type ChvSymptomTriageDraftInput = {
  draftId?: string;
  wardId: number;
  wardPublicId: string;
  diarrhea?: boolean;
  vomiting?: boolean;
  dehydration?: boolean;
  fever?: boolean;
  textInput?: string;
};

export type ChvPreventionVisitDraftInput = {
  draftId?: string;
  taskPublicId?: string;
  actionPublicId?: string;
  visitCompleted?: boolean;
  householdsReachedCount?: number;
  messagesDeliveredCount?: number;
  waterTreatmentDemo?: boolean;
  soapOrHandwashingDiscussed?: boolean;
};

export type ChvPendingSyncItemInput = {
  localId?: string;
  clientSubmissionId?: string;
  idempotencyKey?: string;
  uploadType: ChvOfflineUploadType;
  status?: Extract<ChvOfflineSyncStatus, "PENDING" | "SENDING">;
  payload: Record<string, unknown>;
  draftLocalId?: string | null;
  downloadBundleVersion?: string;
  attemptCount?: number;
  lastAttemptAt?: string | null;
};

function iso(now: Date) {
  return now.toISOString();
}

function addMs(now: Date, ms: number) {
  return new Date(now.getTime() + ms).toISOString();
}

function createLocalId(prefix: string) {
  const cryptoObject = typeof crypto !== "undefined" ? crypto : null;
  if (cryptoObject && "randomUUID" in cryptoObject) {
    return `${prefix}-${cryptoObject.randomUUID()}`;
  }
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function hasExpired(expiresAt: string, now: Date) {
  const expiresAtTime = new Date(expiresAt).getTime();
  if (Number.isNaN(expiresAtTime)) {
    return true;
  }
  return expiresAtTime <= now.getTime();
}

function touch(store: ChvOfflineLocalStore, now: Date): ChvOfflineLocalStore {
  return {
    ...store,
    updatedAt: iso(now),
  };
}

function browserStorage(storage?: Storage) {
  if (storage) {
    return storage;
  }
  if (typeof window === "undefined") {
    return null;
  }
  return window.localStorage;
}

export function getChvOfflineStoreKey(scopeKey: string) {
  return `${CHV_OFFLINE_STORE_KEY_PREFIX}.${encodeURIComponent(scopeKey)}`;
}

export function createEmptyChvOfflineStore(scopeKey: string, now = new Date()): ChvOfflineLocalStore {
  const timestamp = iso(now);
  return {
    schemaVersion: CHV_OFFLINE_LOCAL_SCHEMA_VERSION,
    scopeKey,
    createdAt: timestamp,
    updatedAt: timestamp,
    retentionRules: CHV_OFFLINE_RETENTION_RULES,
    bundleMetadata: null,
    assignedTasks: [],
    wardGuidance: [],
    symptomTriageDrafts: [],
    preventionVisitDrafts: [],
    pendingSyncItems: [],
    failedSyncItems: [],
    conflictItems: [],
    lastSuccessfulSync: null,
  };
}

function normalizeStore(value: unknown, scopeKey: string, now: Date): ChvOfflineLocalStore {
  if (!value || typeof value !== "object") {
    return createEmptyChvOfflineStore(scopeKey, now);
  }

  const candidate = value as Partial<ChvOfflineLocalStore>;
  if (candidate.schemaVersion !== CHV_OFFLINE_LOCAL_SCHEMA_VERSION || candidate.scopeKey !== scopeKey) {
    return createEmptyChvOfflineStore(scopeKey, now);
  }

  return {
    schemaVersion: CHV_OFFLINE_LOCAL_SCHEMA_VERSION,
    scopeKey,
    createdAt: candidate.createdAt || iso(now),
    updatedAt: candidate.updatedAt || iso(now),
    retentionRules: CHV_OFFLINE_RETENTION_RULES,
    bundleMetadata: candidate.bundleMetadata ?? null,
    assignedTasks: Array.isArray(candidate.assignedTasks) ? candidate.assignedTasks : [],
    wardGuidance: Array.isArray(candidate.wardGuidance) ? candidate.wardGuidance : [],
    symptomTriageDrafts: Array.isArray(candidate.symptomTriageDrafts) ? candidate.symptomTriageDrafts : [],
    preventionVisitDrafts: Array.isArray(candidate.preventionVisitDrafts) ? candidate.preventionVisitDrafts : [],
    pendingSyncItems: Array.isArray(candidate.pendingSyncItems) ? candidate.pendingSyncItems : [],
    failedSyncItems: Array.isArray(candidate.failedSyncItems) ? candidate.failedSyncItems : [],
    conflictItems: Array.isArray(candidate.conflictItems) ? candidate.conflictItems : [],
    lastSuccessfulSync: candidate.lastSuccessfulSync ?? null,
  };
}

export function readChvOfflineStore(scopeKey: string, storage?: Storage, now = new Date()) {
  const targetStorage = browserStorage(storage);
  if (!targetStorage) {
    return createEmptyChvOfflineStore(scopeKey, now);
  }

  try {
    const raw = targetStorage.getItem(getChvOfflineStoreKey(scopeKey));
    if (!raw) {
      return createEmptyChvOfflineStore(scopeKey, now);
    }
    return normalizeStore(JSON.parse(raw) as unknown, scopeKey, now);
  } catch {
    return createEmptyChvOfflineStore(scopeKey, now);
  }
}

export function writeChvOfflineStore(store: ChvOfflineLocalStore, storage?: Storage) {
  const targetStorage = browserStorage(storage);
  if (!targetStorage) {
    return store;
  }

  targetStorage.setItem(getChvOfflineStoreKey(store.scopeKey), JSON.stringify(store));
  return store;
}

export function clearChvOfflineStore(scopeKey: string, storage?: Storage) {
  const targetStorage = browserStorage(storage);
  if (!targetStorage) {
    return;
  }
  targetStorage.removeItem(getChvOfflineStoreKey(scopeKey));
}

export function cacheChvOfflineDownloadBundle(
  store: ChvOfflineLocalStore,
  bundle: ChvOfflineDownloadBundleInput,
  contractVersion = "chv-offline-v1",
  now = new Date(),
): ChvOfflineLocalStore {
  const cachedAt = iso(now);
  const downloadBundleVersion = bundle.version;
  const taskExpiresAt = addMs(now, CHV_OFFLINE_RETENTION_RULES.assignedTasksDays * DAYS_TO_MS);

  return touch(
    {
      ...store,
      bundleMetadata: {
        schemaVersion: CHV_OFFLINE_LOCAL_SCHEMA_VERSION,
        contractVersion,
        downloadBundleVersion,
        taskBundleSchemaVersion: bundle.task_bundle.schema_version,
        guidanceBundleSchemaVersion: bundle.guidance_bundle.schema_version,
        ruleBundleVersion: bundle.decision_support_rule_bundle.version,
        generatedAt: bundle.generated_at,
        cachedAt,
        expiresAt: bundle.expires_at,
      },
      assignedTasks: bundle.task_bundle.tasks.map((task) => ({
        schemaVersion: CHV_OFFLINE_LOCAL_SCHEMA_VERSION,
        localId: `task-${task.task_public_id}`,
        scopeKey: store.scopeKey,
        createdAt: cachedAt,
        updatedAt: cachedAt,
        expiresAt: taskExpiresAt,
        taskPublicId: task.task_public_id,
        taskType: task.task_type,
        actionType: task.action_type,
        coverageRequestPublicId: task.coverage_request_public_id,
        status: task.status,
        priority: task.priority,
        wardId: task.ward_id,
        wardPublicId: task.ward_public_id,
        dueAt: task.due_at ?? null,
        startAt: task.start_at ?? null,
        endAt: task.end_at ?? null,
        allowedUploadTypes: task.allowed_upload_types ?? [],
        minimumCapture: task.minimum_capture ?? [],
        downloadBundleVersion,
      })),
      wardGuidance: bundle.guidance_bundle.items.map((guidance) => ({
        schemaVersion: CHV_OFFLINE_LOCAL_SCHEMA_VERSION,
        localId: `guidance-${guidance.guidance_public_id}`,
        scopeKey: store.scopeKey,
        createdAt: cachedAt,
        updatedAt: cachedAt,
        expiresAt: bundle.expires_at,
        guidancePublicId: guidance.guidance_public_id,
        templateKey: guidance.template_key,
        language: guidance.language,
        version: guidance.version,
        audienceType: guidance.audience_type,
        title: guidance.title,
        body: guidance.body,
        publicHealthCaveats: guidance.public_health_caveats ?? "",
        downloadBundleVersion,
      })),
    },
    now,
  );
}

export function describeChvOfflineBundleFreshness(store: ChvOfflineLocalStore, now = new Date()) {
  if (!store.bundleMetadata) {
    return {
      isStale: true,
      reason: "missing_bundle",
      downloadBundleVersion: null,
      expiresAt: null,
    };
  }

  if (hasExpired(store.bundleMetadata.expiresAt, now)) {
    return {
      isStale: true,
      reason: "expired_bundle",
      downloadBundleVersion: store.bundleMetadata.downloadBundleVersion,
      expiresAt: store.bundleMetadata.expiresAt,
    };
  }

  return {
    isStale: false,
    reason: "fresh_bundle",
    downloadBundleVersion: store.bundleMetadata.downloadBundleVersion,
    expiresAt: store.bundleMetadata.expiresAt,
  };
}

export function isChvOfflineBundleStale(store: ChvOfflineLocalStore, now = new Date()) {
  return describeChvOfflineBundleFreshness(store, now).isStale;
}

export function upsertSymptomTriageDraft(
  store: ChvOfflineLocalStore,
  input: ChvSymptomTriageDraftInput,
  now = new Date(),
): ChvOfflineLocalStore {
  const timestamp = iso(now);
  const localId = input.draftId || createLocalId("triage-draft");
  const existing = store.symptomTriageDrafts.find((draft) => draft.localId === localId);
  const draft: ChvSymptomTriageDraft = {
    schemaVersion: CHV_OFFLINE_LOCAL_SCHEMA_VERSION,
    localId,
    scopeKey: store.scopeKey,
    createdAt: existing?.createdAt ?? timestamp,
    updatedAt: timestamp,
    expiresAt: addMs(now, CHV_OFFLINE_RETENTION_RULES.symptomTriageDraftHours * HOURS_TO_MS),
    draftType: "symptom_triage",
    wardId: input.wardId,
    wardPublicId: input.wardPublicId,
    diarrhea: input.diarrhea ?? existing?.diarrhea ?? false,
    vomiting: input.vomiting ?? existing?.vomiting ?? false,
    dehydration: input.dehydration ?? existing?.dehydration ?? false,
    fever: input.fever ?? existing?.fever ?? false,
    textInput: input.textInput ?? existing?.textInput ?? "",
  };

  return touch(
    {
      ...store,
      symptomTriageDrafts: [
        ...store.symptomTriageDrafts.filter((item) => item.localId !== localId),
        draft,
      ],
    },
    now,
  );
}

export function upsertPreventionVisitDraft(
  store: ChvOfflineLocalStore,
  input: ChvPreventionVisitDraftInput,
  now = new Date(),
): ChvOfflineLocalStore {
  const timestamp = iso(now);
  const localId = input.draftId || createLocalId("prevention-draft");
  const existing = store.preventionVisitDrafts.find((draft) => draft.localId === localId);
  const draft: ChvPreventionVisitDraft = {
    schemaVersion: CHV_OFFLINE_LOCAL_SCHEMA_VERSION,
    localId,
    scopeKey: store.scopeKey,
    createdAt: existing?.createdAt ?? timestamp,
    updatedAt: timestamp,
    expiresAt: addMs(now, CHV_OFFLINE_RETENTION_RULES.preventionVisitDraftHours * HOURS_TO_MS),
    draftType: "prevention_visit",
    taskPublicId: input.taskPublicId ?? existing?.taskPublicId ?? "",
    actionPublicId: input.actionPublicId ?? existing?.actionPublicId ?? "",
    visitCompleted: input.visitCompleted ?? existing?.visitCompleted ?? false,
    householdsReachedCount: input.householdsReachedCount ?? existing?.householdsReachedCount ?? 0,
    messagesDeliveredCount: input.messagesDeliveredCount ?? existing?.messagesDeliveredCount ?? 0,
    waterTreatmentDemo: input.waterTreatmentDemo ?? existing?.waterTreatmentDemo ?? false,
    soapOrHandwashingDiscussed:
      input.soapOrHandwashingDiscussed ?? existing?.soapOrHandwashingDiscussed ?? false,
  };

  return touch(
    {
      ...store,
      preventionVisitDrafts: [
        ...store.preventionVisitDrafts.filter((item) => item.localId !== localId),
        draft,
      ],
    },
    now,
  );
}

export function queueChvPendingSyncItem(
  store: ChvOfflineLocalStore,
  input: ChvPendingSyncItemInput,
  now = new Date(),
): ChvOfflineLocalStore {
  const timestamp = iso(now);
  const localId = input.localId || createLocalId("sync");
  const clientSubmissionId = input.clientSubmissionId || localId;
  const item: ChvPendingSyncItem = {
    schemaVersion: CHV_OFFLINE_LOCAL_SCHEMA_VERSION,
    localId,
    scopeKey: store.scopeKey,
    createdAt: timestamp,
    updatedAt: timestamp,
    expiresAt: addMs(now, CHV_OFFLINE_RETENTION_RULES.pendingSyncItemDays * DAYS_TO_MS),
    clientSubmissionId,
    idempotencyKey: input.idempotencyKey || clientSubmissionId,
    uploadType: input.uploadType,
    status: input.status ?? "PENDING",
    payload: input.payload,
    draftLocalId: input.draftLocalId ?? null,
    downloadBundleVersion: input.downloadBundleVersion ?? store.bundleMetadata?.downloadBundleVersion ?? "",
    attemptCount: input.attemptCount ?? 0,
    lastAttemptAt: input.lastAttemptAt ?? null,
  };

  return touch(
    {
      ...store,
      pendingSyncItems: [
        ...store.pendingSyncItems.filter((pending) => pending.localId !== localId),
        item,
      ],
    },
    now,
  );
}

export function movePendingSyncItemToFailed(
  store: ChvOfflineLocalStore,
  localId: string,
  failure: { failureReason: string; serverStatus?: number | null },
  now = new Date(),
): ChvOfflineLocalStore {
  const pending = store.pendingSyncItems.find((item) => item.localId === localId);
  if (!pending) {
    return store;
  }

  const failedAt = iso(now);
  const failedItem: ChvFailedSyncItem = {
    schemaVersion: pending.schemaVersion,
    localId: pending.localId,
    scopeKey: pending.scopeKey,
    createdAt: pending.createdAt,
    clientSubmissionId: pending.clientSubmissionId,
    idempotencyKey: pending.idempotencyKey,
    uploadType: pending.uploadType,
    payload: pending.payload,
    draftLocalId: pending.draftLocalId,
    downloadBundleVersion: pending.downloadBundleVersion,
    attemptCount: pending.attemptCount + 1,
    expiresAt: addMs(now, CHV_OFFLINE_RETENTION_RULES.failedSyncItemDays * DAYS_TO_MS),
    updatedAt: failedAt,
    failedAt,
    failureReason: failure.failureReason,
    serverStatus: failure.serverStatus ?? null,
  };

  return touch(
    {
      ...store,
      pendingSyncItems: store.pendingSyncItems.filter((item) => item.localId !== localId),
      failedSyncItems: [
        ...store.failedSyncItems.filter((item) => item.localId !== localId),
        failedItem,
      ],
    },
    now,
  );
}

export function markChvPendingSyncItemAttempted(
  store: ChvOfflineLocalStore,
  localId: string,
  now = new Date(),
): ChvOfflineLocalStore {
  const pending = store.pendingSyncItems.find((item) => item.localId === localId);
  if (!pending) {
    return store;
  }

  const attemptedAt = iso(now);
  return touch(
    {
      ...store,
      pendingSyncItems: store.pendingSyncItems.map((item) =>
        item.localId === localId
          ? {
              ...item,
              status: "PENDING",
              attemptCount: item.attemptCount + 1,
              lastAttemptAt: attemptedAt,
              updatedAt: attemptedAt,
            }
          : item,
      ),
    },
    now,
  );
}

export function recordChvSyncConflict(
  store: ChvOfflineLocalStore,
  conflict: {
    localId?: string;
    clientSubmissionId: string;
    idempotencyKey: string;
    uploadType: ChvOfflineUploadType;
    conflictState: ChvOfflineConflictState;
    serverReceipt?: Record<string, unknown>;
    resolutionStatus?: "UNRESOLVED" | "RESOLVED" | "DISMISSED";
  },
  now = new Date(),
): ChvOfflineLocalStore {
  const timestamp = iso(now);
  const localId = conflict.localId || `conflict-${conflict.idempotencyKey}`;
  const item: ChvConflictItem = {
    schemaVersion: CHV_OFFLINE_LOCAL_SCHEMA_VERSION,
    localId,
    scopeKey: store.scopeKey,
    createdAt: timestamp,
    updatedAt: timestamp,
    expiresAt: addMs(now, CHV_OFFLINE_RETENTION_RULES.conflictItemDays * DAYS_TO_MS),
    clientSubmissionId: conflict.clientSubmissionId,
    idempotencyKey: conflict.idempotencyKey,
    uploadType: conflict.uploadType,
    conflictState: conflict.conflictState,
    serverReceipt: conflict.serverReceipt ?? {},
    resolutionStatus: conflict.resolutionStatus ?? "UNRESOLVED",
  };

  return touch(
    {
      ...store,
      conflictItems: [
        ...store.conflictItems.filter((existing) => existing.localId !== localId),
        item,
      ],
    },
    now,
  );
}

export function markChvSyncItemSent(
  store: ChvOfflineLocalStore,
  localId: string,
  metadata: Omit<ChvLastSuccessfulSyncMetadata, "schemaVersion" | "scopeKey" | "expiresAt">,
  now = new Date(),
): ChvOfflineLocalStore {
  return touch(
    {
      ...store,
      pendingSyncItems: store.pendingSyncItems.filter((item) => item.localId !== localId),
      lastSuccessfulSync: {
        schemaVersion: CHV_OFFLINE_LOCAL_SCHEMA_VERSION,
        scopeKey: store.scopeKey,
        expiresAt: addMs(now, CHV_OFFLINE_RETENTION_RULES.lastSuccessfulSyncMetadataDays * DAYS_TO_MS),
        ...metadata,
      },
    },
    now,
  );
}

export function markChvAssignedTaskStatus(
  store: ChvOfflineLocalStore,
  taskPublicId: string,
  status: string,
  now = new Date(),
): ChvOfflineLocalStore {
  const timestamp = iso(now);

  return touch(
    {
      ...store,
      assignedTasks: store.assignedTasks.map((task) =>
        task.taskPublicId === taskPublicId
          ? {
              ...task,
              status,
              updatedAt: timestamp,
            }
          : task,
      ),
    },
    now,
  );
}

export function applyChvOfflineRetentionRules(
  store: ChvOfflineLocalStore,
  now = new Date(),
): ChvOfflineLocalStore {
  return touch(
    {
      ...store,
      assignedTasks: store.assignedTasks.filter((item) => !hasExpired(item.expiresAt, now)),
      wardGuidance: store.wardGuidance.filter((item) => !hasExpired(item.expiresAt, now)),
      symptomTriageDrafts: store.symptomTriageDrafts.filter((item) => !hasExpired(item.expiresAt, now)),
      preventionVisitDrafts: store.preventionVisitDrafts.filter((item) => !hasExpired(item.expiresAt, now)),
      pendingSyncItems: store.pendingSyncItems.filter((item) => !hasExpired(item.expiresAt, now)),
      failedSyncItems: store.failedSyncItems.filter((item) => !hasExpired(item.expiresAt, now)),
      conflictItems: store.conflictItems.filter((item) => !hasExpired(item.expiresAt, now)),
      lastSuccessfulSync:
        store.lastSuccessfulSync && !hasExpired(store.lastSuccessfulSync.expiresAt, now)
          ? store.lastSuccessfulSync
          : null,
    },
    now,
  );
}
