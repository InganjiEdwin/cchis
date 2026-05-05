import { normalizeChvLanguage, type ChvSupportedLanguage } from "@/lib/chv-localization";

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
  requestedLanguage: string;
  resolvedLanguage: string;
  fallbackUsed: boolean;
  guidanceContentUnavailable: boolean;
  guidanceGovernanceStatus: string;
  decisionSupportContentUnavailable: boolean;
  decisionSupportGovernanceStatus: string;
  missingDecisionSupportRecommendationKeys: string[];
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
  requestedLanguage: string;
  resolvedLanguage: string;
  fallbackUsed: boolean;
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
  requestedLanguage: string;
  resolvedLanguage: string;
  fallbackUsed: boolean;
  version: number;
  audienceType: string;
  title: string;
  body: string;
  publicHealthCaveats: string;
  downloadBundleVersion: string;
};

export type ChvOfflineDecisionSupportRecommendation = LocalEntityBase & {
  recommendationPublicId: string;
  recommendationKey: string;
  templateKey: string;
  language: string;
  requestedLanguage: string;
  resolvedLanguage: string;
  fallbackUsed: boolean;
  version: number;
  audienceType: string;
  title: string;
  body: string;
  publicHealthCaveats: string;
  source: string;
  governanceStatus: string;
  downloadBundleVersion: string;
};

export type ChvSymptomTriageDraft = LocalEntityBase & {
  draftType: "symptom_triage";
  requestedLanguage: string;
  resolvedLanguage: string;
  fallbackUsed: boolean;
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
  requestedLanguage: string;
  resolvedLanguage: string;
  fallbackUsed: boolean;
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
  requestedLanguage: string;
  resolvedLanguage: string;
  fallbackUsed: boolean;
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
  requestedLanguage: string;
  resolvedLanguage: string;
  fallbackUsed: boolean;
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
  requestedLanguage: string;
  resolvedLanguage: string;
  fallbackUsed: boolean;
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
  requestedLanguage: string;
  resolvedLanguage: string;
  fallbackUsed: boolean;
  pendingUploadCount: number;
  failedUploadCount: number;
  syncHealth: "ONLINE" | "DELAYED" | "OFFLINE";
  expiresAt: string;
};

export type ChvOfflineLocalStore = {
  schemaVersion: typeof CHV_OFFLINE_LOCAL_SCHEMA_VERSION;
  scopeKey: string;
  selectedLanguage: ChvSupportedLanguage;
  createdAt: string;
  updatedAt: string;
  retentionRules: typeof CHV_OFFLINE_RETENTION_RULES;
  bundleMetadata: ChvOfflineBundleMetadata | null;
  assignedTasks: ChvOfflineAssignedTask[];
  wardGuidance: ChvOfflineWardGuidance[];
  decisionSupportRecommendations: ChvOfflineDecisionSupportRecommendation[];
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
  requested_language?: string;
  resolved_language?: string;
  fallback_used?: boolean;
  task_bundle: {
    schema_version: string;
    requested_language?: string;
    resolved_language?: string;
    fallback_used?: boolean;
    language?: {
      requested_language?: string;
      resolved_language?: string;
      fallback_used?: boolean;
    };
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
    requested_language?: string;
    resolved_language?: string;
    fallback_used?: boolean;
    content_unavailable?: boolean;
    governance_status?: string;
    items: Array<{
      guidance_public_id: string;
      template_key: string;
      language: string;
      requested_language?: string;
      resolved_language?: string;
      fallback_used?: boolean;
      version: number;
      audience_type: string;
      title: string;
      body: string;
      public_health_caveats?: string;
    }>;
  };
  decision_support_rule_bundle: {
    version: string;
    requested_language?: string;
    resolved_language?: string;
    fallback_used?: boolean;
    content_unavailable?: boolean;
    governance_status?: string;
    missing_recommendation_keys?: string[];
    recommendations?: Array<{
      recommendation_public_id?: string;
      recommendation_key: string;
      template_key: string;
      language: string;
      requested_language?: string;
      resolved_language?: string;
      fallback_used?: boolean;
      version: number;
      audience_type?: string;
      title: string;
      body: string;
      public_health_caveats?: string;
      source?: string;
      governance_status?: string;
    }>;
  };
};

export type ChvSymptomTriageDraftInput = {
  draftId?: string;
  requestedLanguage?: string;
  resolvedLanguage?: string;
  fallbackUsed?: boolean;
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
  requestedLanguage?: string;
  resolvedLanguage?: string;
  fallbackUsed?: boolean;
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
  requestedLanguage?: string;
  resolvedLanguage?: string;
  fallbackUsed?: boolean;
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

function languageMetadataForStore(
  store: Pick<ChvOfflineLocalStore, "selectedLanguage" | "bundleMetadata">,
  input: { requestedLanguage?: string; resolvedLanguage?: string; fallbackUsed?: boolean } = {},
) {
  const requestedLanguage = normalizeChvLanguage(
    input.requestedLanguage ?? store.bundleMetadata?.requestedLanguage ?? store.selectedLanguage,
  );
  const resolvedLanguage = normalizeChvLanguage(
    input.resolvedLanguage ?? store.bundleMetadata?.resolvedLanguage ?? requestedLanguage,
  );
  return {
    requestedLanguage,
    resolvedLanguage,
    fallbackUsed: Boolean(input.fallbackUsed ?? store.bundleMetadata?.fallbackUsed ?? requestedLanguage !== resolvedLanguage),
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

export function createEmptyChvOfflineStore(
  scopeKey: string,
  now = new Date(),
  selectedLanguage: ChvSupportedLanguage = "en",
): ChvOfflineLocalStore {
  const timestamp = iso(now);
  return {
    schemaVersion: CHV_OFFLINE_LOCAL_SCHEMA_VERSION,
    scopeKey,
    selectedLanguage,
    createdAt: timestamp,
    updatedAt: timestamp,
    retentionRules: CHV_OFFLINE_RETENTION_RULES,
    bundleMetadata: null,
    assignedTasks: [],
    wardGuidance: [],
    decisionSupportRecommendations: [],
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

  const selectedLanguage = normalizeChvLanguage(
    candidate.selectedLanguage ?? candidate.bundleMetadata?.requestedLanguage ?? candidate.bundleMetadata?.resolvedLanguage,
  );
  const bundleMetadata = candidate.bundleMetadata
    ? {
        ...candidate.bundleMetadata,
        requestedLanguage: normalizeChvLanguage(candidate.bundleMetadata.requestedLanguage ?? selectedLanguage),
        resolvedLanguage: normalizeChvLanguage(candidate.bundleMetadata.resolvedLanguage ?? selectedLanguage),
        fallbackUsed: candidate.bundleMetadata.fallbackUsed ?? false,
        guidanceContentUnavailable: Boolean(candidate.bundleMetadata.guidanceContentUnavailable ?? false),
        guidanceGovernanceStatus: candidate.bundleMetadata.guidanceGovernanceStatus ?? "unknown",
        decisionSupportContentUnavailable: Boolean(candidate.bundleMetadata.decisionSupportContentUnavailable ?? false),
        decisionSupportGovernanceStatus: candidate.bundleMetadata.decisionSupportGovernanceStatus ?? "unknown",
        missingDecisionSupportRecommendationKeys: Array.isArray(
          candidate.bundleMetadata.missingDecisionSupportRecommendationKeys,
        )
          ? candidate.bundleMetadata.missingDecisionSupportRecommendationKeys
          : [],
      }
    : null;
  const lastSuccessfulSync = candidate.lastSuccessfulSync
    ? {
        ...candidate.lastSuccessfulSync,
        requestedLanguage: normalizeChvLanguage(candidate.lastSuccessfulSync.requestedLanguage ?? selectedLanguage),
        resolvedLanguage: normalizeChvLanguage(candidate.lastSuccessfulSync.resolvedLanguage ?? selectedLanguage),
        fallbackUsed: candidate.lastSuccessfulSync.fallbackUsed ?? false,
      }
    : null;
  const storeLanguageMetadata = languageMetadataForStore({ selectedLanguage, bundleMetadata });

  return {
    schemaVersion: CHV_OFFLINE_LOCAL_SCHEMA_VERSION,
    scopeKey,
    selectedLanguage,
    createdAt: candidate.createdAt || iso(now),
    updatedAt: candidate.updatedAt || iso(now),
    retentionRules: CHV_OFFLINE_RETENTION_RULES,
    bundleMetadata,
    assignedTasks: Array.isArray(candidate.assignedTasks)
      ? candidate.assignedTasks.map((task) => ({
          ...task,
          requestedLanguage: normalizeChvLanguage(task.requestedLanguage ?? storeLanguageMetadata.requestedLanguage),
          resolvedLanguage: normalizeChvLanguage(task.resolvedLanguage ?? storeLanguageMetadata.resolvedLanguage),
          fallbackUsed: task.fallbackUsed ?? storeLanguageMetadata.fallbackUsed,
        }))
      : [],
    wardGuidance: Array.isArray(candidate.wardGuidance)
      ? candidate.wardGuidance.map((guidance) => ({
          ...guidance,
          requestedLanguage: normalizeChvLanguage(guidance.requestedLanguage ?? guidance.language ?? selectedLanguage),
          resolvedLanguage: normalizeChvLanguage(guidance.resolvedLanguage ?? guidance.language ?? selectedLanguage),
          fallbackUsed: guidance.fallbackUsed ?? false,
        }))
      : [],
    decisionSupportRecommendations: Array.isArray(candidate.decisionSupportRecommendations)
      ? candidate.decisionSupportRecommendations.map((recommendation) => ({
          ...recommendation,
          language: normalizeChvLanguage(recommendation.language ?? storeLanguageMetadata.resolvedLanguage),
          requestedLanguage: normalizeChvLanguage(
            recommendation.requestedLanguage ?? storeLanguageMetadata.requestedLanguage,
          ),
          resolvedLanguage: normalizeChvLanguage(
            recommendation.resolvedLanguage ?? recommendation.language ?? storeLanguageMetadata.resolvedLanguage,
          ),
          fallbackUsed: recommendation.fallbackUsed ?? storeLanguageMetadata.fallbackUsed,
        }))
      : [],
    symptomTriageDrafts: Array.isArray(candidate.symptomTriageDrafts)
      ? candidate.symptomTriageDrafts.map((draft) => ({
          ...draft,
          requestedLanguage: normalizeChvLanguage(draft.requestedLanguage ?? storeLanguageMetadata.requestedLanguage),
          resolvedLanguage: normalizeChvLanguage(draft.resolvedLanguage ?? storeLanguageMetadata.resolvedLanguage),
          fallbackUsed: draft.fallbackUsed ?? storeLanguageMetadata.fallbackUsed,
        }))
      : [],
    preventionVisitDrafts: Array.isArray(candidate.preventionVisitDrafts)
      ? candidate.preventionVisitDrafts.map((draft) => ({
          ...draft,
          requestedLanguage: normalizeChvLanguage(draft.requestedLanguage ?? storeLanguageMetadata.requestedLanguage),
          resolvedLanguage: normalizeChvLanguage(draft.resolvedLanguage ?? storeLanguageMetadata.resolvedLanguage),
          fallbackUsed: draft.fallbackUsed ?? storeLanguageMetadata.fallbackUsed,
        }))
      : [],
    pendingSyncItems: Array.isArray(candidate.pendingSyncItems)
      ? candidate.pendingSyncItems.map((item) => ({
          ...item,
          requestedLanguage: normalizeChvLanguage(item.requestedLanguage ?? storeLanguageMetadata.requestedLanguage),
          resolvedLanguage: normalizeChvLanguage(item.resolvedLanguage ?? storeLanguageMetadata.resolvedLanguage),
          fallbackUsed: item.fallbackUsed ?? storeLanguageMetadata.fallbackUsed,
        }))
      : [],
    failedSyncItems: Array.isArray(candidate.failedSyncItems)
      ? candidate.failedSyncItems.map((item) => ({
          ...item,
          requestedLanguage: normalizeChvLanguage(item.requestedLanguage ?? storeLanguageMetadata.requestedLanguage),
          resolvedLanguage: normalizeChvLanguage(item.resolvedLanguage ?? storeLanguageMetadata.resolvedLanguage),
          fallbackUsed: item.fallbackUsed ?? storeLanguageMetadata.fallbackUsed,
        }))
      : [],
    conflictItems: Array.isArray(candidate.conflictItems)
      ? candidate.conflictItems.map((item) => ({
          ...item,
          requestedLanguage: normalizeChvLanguage(item.requestedLanguage ?? storeLanguageMetadata.requestedLanguage),
          resolvedLanguage: normalizeChvLanguage(item.resolvedLanguage ?? storeLanguageMetadata.resolvedLanguage),
          fallbackUsed: item.fallbackUsed ?? storeLanguageMetadata.fallbackUsed,
        }))
      : [],
    lastSuccessfulSync,
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

export function setChvOfflineSelectedLanguage(
  store: ChvOfflineLocalStore,
  language: string,
  now = new Date(),
): ChvOfflineLocalStore {
  return touch(
    {
      ...store,
      selectedLanguage: normalizeChvLanguage(language),
    },
    now,
  );
}

export function markChvOfflineCachedBundleLanguageFallback(
  store: ChvOfflineLocalStore,
  requestedLanguage: string,
  now = new Date(),
): ChvOfflineLocalStore {
  const language = normalizeChvLanguage(requestedLanguage);
  if (!store.bundleMetadata) {
    return setChvOfflineSelectedLanguage(store, language, now);
  }
  const bundleMetadata = {
    ...store.bundleMetadata,
    requestedLanguage: language,
    fallbackUsed: store.bundleMetadata.fallbackUsed || store.bundleMetadata.resolvedLanguage !== language,
  };
  return touch(
    {
      ...store,
      selectedLanguage: language,
      bundleMetadata,
      assignedTasks: store.assignedTasks.map((task) => ({
        ...task,
        requestedLanguage: language,
        fallbackUsed: task.fallbackUsed || task.resolvedLanguage !== language,
      })),
      wardGuidance: store.wardGuidance.map((guidance) => ({
        ...guidance,
        requestedLanguage: language,
        fallbackUsed: guidance.fallbackUsed || guidance.resolvedLanguage !== language,
      })),
      decisionSupportRecommendations: store.decisionSupportRecommendations.map((recommendation) => ({
        ...recommendation,
        requestedLanguage: language,
        fallbackUsed: recommendation.fallbackUsed || recommendation.resolvedLanguage !== language,
      })),
    },
    now,
  );
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
  const bundleLanguage = {
    requestedLanguage: normalizeChvLanguage(
      bundle.requested_language ?? bundle.guidance_bundle.requested_language ?? store.selectedLanguage,
    ),
    resolvedLanguage: normalizeChvLanguage(
      bundle.resolved_language ?? bundle.guidance_bundle.resolved_language ?? store.selectedLanguage,
    ),
    fallbackUsed: Boolean(bundle.fallback_used ?? bundle.guidance_bundle.fallback_used ?? false),
  };
  const taskLanguage = {
    requestedLanguage: normalizeChvLanguage(
      bundle.task_bundle.requested_language
        ?? bundle.task_bundle.language?.requested_language
        ?? bundleLanguage.requestedLanguage,
    ),
    resolvedLanguage: normalizeChvLanguage(
      bundle.task_bundle.resolved_language
        ?? bundle.task_bundle.language?.resolved_language
        ?? bundleLanguage.resolvedLanguage,
    ),
    fallbackUsed: Boolean(
      bundle.task_bundle.fallback_used
        ?? bundle.task_bundle.language?.fallback_used
        ?? bundleLanguage.fallbackUsed,
    ),
  };
  const ruleLanguage = {
    requestedLanguage: normalizeChvLanguage(
      bundle.decision_support_rule_bundle.requested_language ?? bundleLanguage.requestedLanguage,
    ),
    resolvedLanguage: normalizeChvLanguage(
      bundle.decision_support_rule_bundle.resolved_language ?? bundleLanguage.resolvedLanguage,
    ),
    fallbackUsed: Boolean(bundle.decision_support_rule_bundle.fallback_used ?? bundleLanguage.fallbackUsed),
  };

  return touch(
    {
      ...store,
      selectedLanguage: bundleLanguage.requestedLanguage,
      bundleMetadata: {
        schemaVersion: CHV_OFFLINE_LOCAL_SCHEMA_VERSION,
        contractVersion,
        downloadBundleVersion,
        requestedLanguage: bundleLanguage.requestedLanguage,
        resolvedLanguage: bundleLanguage.resolvedLanguage,
        fallbackUsed: bundleLanguage.fallbackUsed,
        guidanceContentUnavailable: Boolean(bundle.guidance_bundle.content_unavailable ?? false),
        guidanceGovernanceStatus: bundle.guidance_bundle.governance_status ?? "unknown",
        decisionSupportContentUnavailable: Boolean(bundle.decision_support_rule_bundle.content_unavailable ?? false),
        decisionSupportGovernanceStatus: bundle.decision_support_rule_bundle.governance_status ?? "unknown",
        missingDecisionSupportRecommendationKeys: bundle.decision_support_rule_bundle.missing_recommendation_keys ?? [],
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
        requestedLanguage: taskLanguage.requestedLanguage,
        resolvedLanguage: taskLanguage.resolvedLanguage,
        fallbackUsed: taskLanguage.fallbackUsed,
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
        language: normalizeChvLanguage(guidance.language),
        requestedLanguage: normalizeChvLanguage(
          guidance.requested_language ?? bundle.guidance_bundle.requested_language ?? bundle.requested_language ?? store.selectedLanguage,
        ),
        resolvedLanguage: normalizeChvLanguage(guidance.resolved_language ?? guidance.language),
        fallbackUsed: Boolean(guidance.fallback_used ?? guidance.language !== (bundle.requested_language ?? guidance.language)),
        version: guidance.version,
        audienceType: guidance.audience_type,
        title: guidance.title,
        body: guidance.body,
        publicHealthCaveats: guidance.public_health_caveats ?? "",
        downloadBundleVersion,
      })),
      decisionSupportRecommendations: (bundle.decision_support_rule_bundle.recommendations ?? []).map((recommendation) => ({
        schemaVersion: CHV_OFFLINE_LOCAL_SCHEMA_VERSION,
        localId: `decision-support-${recommendation.recommendation_public_id ?? recommendation.recommendation_key}`,
        scopeKey: store.scopeKey,
        createdAt: cachedAt,
        updatedAt: cachedAt,
        expiresAt: bundle.expires_at,
        recommendationPublicId: recommendation.recommendation_public_id ?? recommendation.recommendation_key,
        recommendationKey: recommendation.recommendation_key,
        templateKey: recommendation.template_key,
        language: normalizeChvLanguage(recommendation.language),
        requestedLanguage: normalizeChvLanguage(
          recommendation.requested_language
            ?? bundle.decision_support_rule_bundle.requested_language
            ?? bundle.requested_language
            ?? store.selectedLanguage,
        ),
        resolvedLanguage: normalizeChvLanguage(recommendation.resolved_language ?? recommendation.language),
        fallbackUsed: Boolean(
          recommendation.fallback_used
            ?? bundle.decision_support_rule_bundle.fallback_used
            ?? recommendation.language !== ruleLanguage.requestedLanguage,
        ),
        version: recommendation.version,
        audienceType: recommendation.audience_type ?? "chv",
        title: recommendation.title,
        body: recommendation.body,
        publicHealthCaveats: recommendation.public_health_caveats ?? "",
        source: recommendation.source ?? "governed_message_template",
        governanceStatus: recommendation.governance_status ?? "approved",
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
  const language = languageMetadataForStore(store, input);
  const draft: ChvSymptomTriageDraft = {
    schemaVersion: CHV_OFFLINE_LOCAL_SCHEMA_VERSION,
    localId,
    scopeKey: store.scopeKey,
    createdAt: existing?.createdAt ?? timestamp,
    updatedAt: timestamp,
    expiresAt: addMs(now, CHV_OFFLINE_RETENTION_RULES.symptomTriageDraftHours * HOURS_TO_MS),
    draftType: "symptom_triage",
    requestedLanguage: existing?.requestedLanguage ?? language.requestedLanguage,
    resolvedLanguage: existing?.resolvedLanguage ?? language.resolvedLanguage,
    fallbackUsed: existing?.fallbackUsed ?? language.fallbackUsed,
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
  const language = languageMetadataForStore(store, input);
  const draft: ChvPreventionVisitDraft = {
    schemaVersion: CHV_OFFLINE_LOCAL_SCHEMA_VERSION,
    localId,
    scopeKey: store.scopeKey,
    createdAt: existing?.createdAt ?? timestamp,
    updatedAt: timestamp,
    expiresAt: addMs(now, CHV_OFFLINE_RETENTION_RULES.preventionVisitDraftHours * HOURS_TO_MS),
    draftType: "prevention_visit",
    requestedLanguage: existing?.requestedLanguage ?? language.requestedLanguage,
    resolvedLanguage: existing?.resolvedLanguage ?? language.resolvedLanguage,
    fallbackUsed: existing?.fallbackUsed ?? language.fallbackUsed,
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
  const language = languageMetadataForStore(store, input);
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
    requestedLanguage: language.requestedLanguage,
    resolvedLanguage: language.resolvedLanguage,
    fallbackUsed: language.fallbackUsed,
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
    requestedLanguage: pending.requestedLanguage,
    resolvedLanguage: pending.resolvedLanguage,
    fallbackUsed: pending.fallbackUsed,
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
    requestedLanguage?: string;
    resolvedLanguage?: string;
    fallbackUsed?: boolean;
    conflictState: ChvOfflineConflictState;
    serverReceipt?: Record<string, unknown>;
    resolutionStatus?: "UNRESOLVED" | "RESOLVED" | "DISMISSED";
  },
  now = new Date(),
): ChvOfflineLocalStore {
  const timestamp = iso(now);
  const localId = conflict.localId || `conflict-${conflict.idempotencyKey}`;
  const language = languageMetadataForStore(store, conflict);
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
    requestedLanguage: language.requestedLanguage,
    resolvedLanguage: language.resolvedLanguage,
    fallbackUsed: language.fallbackUsed,
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
      decisionSupportRecommendations: store.decisionSupportRecommendations.filter((item) => !hasExpired(item.expiresAt, now)),
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
