import { describe, expect, it, beforeEach } from "vitest";

import {
  CHV_OFFLINE_LOCAL_SCHEMA_VERSION,
  CHV_OFFLINE_RETENTION_RULES,
  applyChvOfflineRetentionRules,
  cacheChvOfflineDownloadBundle,
  clearChvOfflineStore,
  createEmptyChvOfflineStore,
  describeChvOfflineBundleFreshness,
  getChvOfflineStoreKey,
  isChvOfflineBundleStale,
  markChvOfflineCachedBundleLanguageFallback,
  markChvPendingSyncItemAttempted,
  markChvSyncItemSent,
  movePendingSyncItemToFailed,
  queueChvPendingSyncItem,
  readChvOfflineStore,
  recordChvSyncConflict,
  setChvOfflineSelectedLanguage,
  upsertPreventionVisitDraft,
  upsertSymptomTriageDraft,
  writeChvOfflineStore,
  type ChvOfflineDownloadBundleInput,
} from "@/lib/chv-offline-store";

const scopeKey = "ward:ward-public-1:chv:chv-public-1";
const baseNow = new Date("2026-05-04T08:00:00.000Z");
let storage: Storage;

function createMemoryStorage(): Storage {
  const values = new Map<string, string>();
  return {
    get length() {
      return values.size;
    },
    clear() {
      values.clear();
    },
    getItem(key: string) {
      return values.get(key) ?? null;
    },
    key(index: number) {
      return Array.from(values.keys())[index] ?? null;
    },
    removeItem(key: string) {
      values.delete(key);
    },
    setItem(key: string, value: string) {
      values.set(key, value);
    },
  };
}

function bundle(overrides: Partial<ChvOfflineDownloadBundleInput> = {}): ChvOfflineDownloadBundleInput {
  return {
    version: "chv-bundle-phase2",
    generated_at: "2026-05-04T07:50:00.000Z",
    expires_at: "2026-05-05T07:50:00.000Z",
    requested_language: "en",
    resolved_language: "en",
    fallback_used: false,
    task_bundle: {
      schema_version: "chv-task-bundle-v1",
      tasks: [
        {
          task_public_id: "task-public-1",
          task_type: "preparedness_action",
          action_type: "chv_follow_up",
          status: "ASSIGNED",
          priority: "HIGH",
          ward_id: 12,
          ward_public_id: "ward-public-1",
          due_at: "2026-05-04T12:00:00.000Z",
          allowed_upload_types: ["task_ack", "prevention_visit"],
          minimum_capture: ["task_public_id", "status", "recorded_at"],
        },
      ],
    },
    guidance_bundle: {
      schema_version: "chv-guidance-bundle-v1",
      requested_language: "en",
      resolved_language: "en",
      fallback_used: false,
      content_unavailable: false,
      governance_status: "approved",
      items: [
        {
          guidance_public_id: "guidance-public-1",
          template_key: "cholera.household.prevention_guidance_offline_bundle",
          language: "en",
          requested_language: "en",
          resolved_language: "en",
          fallback_used: false,
          version: 1,
          audience_type: "chv",
          title: "Core cholera prevention guidance",
          body: "Use safe water and prepare ORS for dehydration risk.",
          public_health_caveats: "Approved offline CHV guidance.",
        },
      ],
    },
    decision_support_rule_bundle: {
      version: "cholera-triage-rules-v1",
      requested_language: "en",
      resolved_language: "en",
      fallback_used: false,
      content_unavailable: false,
      governance_status: "approved",
      missing_recommendation_keys: [],
      recommendations: [
        {
          recommendation_public_id: "recommendation-public-1",
          recommendation_key: "urgent_referral",
          template_key: "cholera.chv.triage.urgent_referral_offline",
          language: "en",
          requested_language: "en",
          resolved_language: "en",
          fallback_used: false,
          version: 1,
          audience_type: "chv",
          title: "Refer now",
          body: "Dehydration signs need facility review.",
          public_health_caveats: "Approved offline CHV triage recommendation.",
          source: "governed_message_template",
          governance_status: "approved",
        },
      ],
    },
    ...overrides,
  };
}

describe("CHV offline local data model", () => {
  beforeEach(() => {
    storage = createMemoryStorage();
  });

  it("initializes and persists a versioned local store", () => {
    const store = createEmptyChvOfflineStore(scopeKey, baseNow);

    expect(store.schemaVersion).toBe(CHV_OFFLINE_LOCAL_SCHEMA_VERSION);
    expect(store.scopeKey).toBe(scopeKey);
    expect(store.selectedLanguage).toBe("en");
    expect(store.assignedTasks).toEqual([]);
    expect(store.wardGuidance).toEqual([]);
    expect(store.decisionSupportRecommendations).toEqual([]);
    expect(store.symptomTriageDrafts).toEqual([]);
    expect(store.preventionVisitDrafts).toEqual([]);
    expect(store.pendingSyncItems).toEqual([]);
    expect(store.failedSyncItems).toEqual([]);
    expect(store.conflictItems).toEqual([]);
    expect(store.lastSuccessfulSync).toBeNull();
    expect(store.retentionRules.symptomTriageDraftHours).toBe(24);

    writeChvOfflineStore(store, storage);
    expect(storage.getItem(getChvOfflineStoreKey(scopeKey))).toContain(scopeKey);
    expect(readChvOfflineStore(scopeKey, storage, baseNow)).toEqual(store);

    clearChvOfflineStore(scopeKey, storage);
    expect(storage.getItem(getChvOfflineStoreKey(scopeKey))).toBeNull();
  });

  it("drops incompatible local schemas instead of reading stale shapes", () => {
    storage.setItem(
      getChvOfflineStoreKey(scopeKey),
      JSON.stringify({ schemaVersion: 999, scopeKey, assignedTasks: [{ taskPublicId: "old" }] }),
    );

    const store = readChvOfflineStore(scopeKey, storage, baseNow);

    expect(store.schemaVersion).toBe(CHV_OFFLINE_LOCAL_SCHEMA_VERSION);
    expect(store.assignedTasks).toEqual([]);
    expect(store.createdAt).toBe(baseNow.toISOString());
  });

  it("caches assigned tasks and ward guidance from a download bundle", () => {
    const store = cacheChvOfflineDownloadBundle(createEmptyChvOfflineStore(scopeKey, baseNow), bundle(), "chv-offline-v1", baseNow);

    expect(store.bundleMetadata?.downloadBundleVersion).toBe("chv-bundle-phase2");
    expect(store.bundleMetadata?.requestedLanguage).toBe("en");
    expect(store.bundleMetadata?.resolvedLanguage).toBe("en");
    expect(store.bundleMetadata?.fallbackUsed).toBe(false);
    expect(store.bundleMetadata?.guidanceContentUnavailable).toBe(false);
    expect(store.bundleMetadata?.guidanceGovernanceStatus).toBe("approved");
    expect(store.bundleMetadata?.decisionSupportContentUnavailable).toBe(false);
    expect(store.bundleMetadata?.decisionSupportGovernanceStatus).toBe("approved");
    expect(store.bundleMetadata?.missingDecisionSupportRecommendationKeys).toEqual([]);
    expect(store.bundleMetadata?.taskBundleSchemaVersion).toBe("chv-task-bundle-v1");
    expect(store.bundleMetadata?.guidanceBundleSchemaVersion).toBe("chv-guidance-bundle-v1");
    expect(store.assignedTasks).toHaveLength(1);
    expect(store.assignedTasks[0]).toMatchObject({
      schemaVersion: CHV_OFFLINE_LOCAL_SCHEMA_VERSION,
      taskPublicId: "task-public-1",
      taskType: "preparedness_action",
      requestedLanguage: "en",
      resolvedLanguage: "en",
      fallbackUsed: false,
      wardId: 12,
      allowedUploadTypes: ["task_ack", "prevention_visit"],
      downloadBundleVersion: "chv-bundle-phase2",
    });
    expect(store.wardGuidance).toHaveLength(1);
    expect(store.wardGuidance[0]).toMatchObject({
      schemaVersion: CHV_OFFLINE_LOCAL_SCHEMA_VERSION,
      guidancePublicId: "guidance-public-1",
      templateKey: "cholera.household.prevention_guidance_offline_bundle",
      requestedLanguage: "en",
      resolvedLanguage: "en",
      fallbackUsed: false,
      downloadBundleVersion: "chv-bundle-phase2",
    });
    expect(store.decisionSupportRecommendations).toHaveLength(1);
    expect(store.decisionSupportRecommendations[0]).toMatchObject({
      schemaVersion: CHV_OFFLINE_LOCAL_SCHEMA_VERSION,
      recommendationKey: "urgent_referral",
      templateKey: "cholera.chv.triage.urgent_referral_offline",
      requestedLanguage: "en",
      resolvedLanguage: "en",
      fallbackUsed: false,
      governanceStatus: "approved",
      downloadBundleVersion: "chv-bundle-phase2",
    });
  });

  it("preserves fail-closed governed content unavailable metadata", () => {
    const store = cacheChvOfflineDownloadBundle(
      createEmptyChvOfflineStore(scopeKey, baseNow),
      bundle({
        guidance_bundle: {
          ...bundle().guidance_bundle,
          content_unavailable: true,
          governance_status: "no_approved_guidance_templates",
          items: [],
        },
        decision_support_rule_bundle: {
          ...bundle().decision_support_rule_bundle,
          content_unavailable: true,
          governance_status: "missing_required_recommendation_templates",
          missing_recommendation_keys: ["urgent_referral"],
          recommendations: [],
        },
      }),
      "chv-offline-v1",
      baseNow,
    );

    expect(store.bundleMetadata).toMatchObject({
      guidanceContentUnavailable: true,
      guidanceGovernanceStatus: "no_approved_guidance_templates",
      decisionSupportContentUnavailable: true,
      decisionSupportGovernanceStatus: "missing_required_recommendation_templates",
      missingDecisionSupportRecommendationKeys: ["urgent_referral"],
    });
    expect(store.wardGuidance).toEqual([]);
    expect(store.decisionSupportRecommendations).toEqual([]);
  });

  it("caches selected language and marks English fallback when translated guidance is missing", () => {
    let store = createEmptyChvOfflineStore(scopeKey, baseNow);
    store = setChvOfflineSelectedLanguage(store, "sw", baseNow);
    store = cacheChvOfflineDownloadBundle(
      store,
      bundle({
        version: "chv-bundle-sw-fallback",
        requested_language: "sw",
        resolved_language: "en",
        fallback_used: true,
        guidance_bundle: {
          ...bundle().guidance_bundle,
          requested_language: "sw",
          resolved_language: "en",
          fallback_used: true,
          items: bundle().guidance_bundle.items.map((item) => ({
            ...item,
            requested_language: "sw",
            resolved_language: "en",
            fallback_used: true,
          })),
        },
      }),
      "chv-offline-v1",
      baseNow,
    );

    expect(store.selectedLanguage).toBe("sw");
    expect(store.bundleMetadata).toMatchObject({
      requestedLanguage: "sw",
      resolvedLanguage: "en",
      fallbackUsed: true,
    });
    expect(store.assignedTasks[0]).toMatchObject({
      requestedLanguage: "sw",
      resolvedLanguage: "en",
      fallbackUsed: true,
    });
    expect(store.wardGuidance[0]).toMatchObject({
      requestedLanguage: "sw",
      resolvedLanguage: "en",
      fallbackUsed: true,
    });

    writeChvOfflineStore(store, storage);
    expect(readChvOfflineStore(scopeKey, storage, baseNow).selectedLanguage).toBe("sw");
  });

  it("uses task bundle language metadata separately from guidance fallback", () => {
    const store = cacheChvOfflineDownloadBundle(
      setChvOfflineSelectedLanguage(createEmptyChvOfflineStore(scopeKey, baseNow), "sw", baseNow),
      bundle({
        requested_language: "sw",
        resolved_language: "en",
        fallback_used: true,
        task_bundle: {
          ...bundle().task_bundle,
          requested_language: "sw",
          resolved_language: "sw",
          fallback_used: false,
        },
        guidance_bundle: {
          ...bundle().guidance_bundle,
          requested_language: "sw",
          resolved_language: "en",
          fallback_used: true,
        },
      }),
      "chv-offline-v1",
      baseNow,
    );

    expect(store.bundleMetadata).toMatchObject({
      requestedLanguage: "sw",
      resolvedLanguage: "en",
      fallbackUsed: true,
    });
    expect(store.assignedTasks[0]).toMatchObject({
      requestedLanguage: "sw",
      resolvedLanguage: "sw",
      fallbackUsed: false,
    });
  });

  it("marks an existing cached bundle as fallback when language changes offline", () => {
    let store = cacheChvOfflineDownloadBundle(
      createEmptyChvOfflineStore(scopeKey, baseNow),
      bundle(),
      "chv-offline-v1",
      baseNow,
    );

    store = markChvOfflineCachedBundleLanguageFallback(store, "luo", new Date("2026-05-04T09:00:00.000Z"));

    expect(store.selectedLanguage).toBe("luo");
    expect(store.bundleMetadata).toMatchObject({
      requestedLanguage: "luo",
      resolvedLanguage: "en",
      fallbackUsed: true,
    });
    expect(store.assignedTasks[0]).toMatchObject({
      requestedLanguage: "luo",
      resolvedLanguage: "en",
      fallbackUsed: true,
    });
    expect(store.wardGuidance[0]).toMatchObject({
      requestedLanguage: "luo",
      resolvedLanguage: "en",
      fallbackUsed: true,
    });
    expect(store.decisionSupportRecommendations[0]).toMatchObject({
      requestedLanguage: "luo",
      resolvedLanguage: "en",
      fallbackUsed: true,
    });
  });

  it("detects missing and expired download bundles", () => {
    const emptyStore = createEmptyChvOfflineStore(scopeKey, baseNow);
    expect(isChvOfflineBundleStale(emptyStore, baseNow)).toBe(true);
    expect(describeChvOfflineBundleFreshness(emptyStore, baseNow).reason).toBe("missing_bundle");

    const freshStore = cacheChvOfflineDownloadBundle(emptyStore, bundle(), "chv-offline-v1", baseNow);
    expect(isChvOfflineBundleStale(freshStore, new Date("2026-05-04T12:00:00.000Z"))).toBe(false);
    expect(describeChvOfflineBundleFreshness(freshStore, new Date("2026-05-06T08:00:00.000Z"))).toMatchObject({
      isStale: true,
      reason: "expired_bundle",
      downloadBundleVersion: "chv-bundle-phase2",
    });

    const translatedStore = cacheChvOfflineDownloadBundle(
      setChvOfflineSelectedLanguage(emptyStore, "luo", baseNow),
      bundle({
        version: "chv-bundle-luo",
        requested_language: "luo",
        resolved_language: "luo",
        guidance_bundle: {
          ...bundle().guidance_bundle,
          requested_language: "luo",
          resolved_language: "luo",
          items: bundle().guidance_bundle.items.map((item) => ({
            ...item,
            language: "luo",
            requested_language: "luo",
            resolved_language: "luo",
          })),
        },
      }),
      "chv-offline-v1",
      baseNow,
    );
    expect(describeChvOfflineBundleFreshness(translatedStore, new Date("2026-05-06T08:00:00.000Z"))).toMatchObject({
      isStale: true,
      reason: "expired_bundle",
      downloadBundleVersion: "chv-bundle-luo",
    });
  });

  it("stores versioned drafts and pending sync envelopes without direct household identifiers", () => {
    let store = createEmptyChvOfflineStore(scopeKey, baseNow);
    store = cacheChvOfflineDownloadBundle(
      setChvOfflineSelectedLanguage(store, "sw", baseNow),
      bundle({
        requested_language: "sw",
        resolved_language: "en",
        fallback_used: true,
        guidance_bundle: {
          ...bundle().guidance_bundle,
          requested_language: "sw",
          resolved_language: "en",
          fallback_used: true,
        },
      }),
      "chv-offline-v1",
      baseNow,
    );
    store = upsertSymptomTriageDraft(
      store,
      {
        draftId: "triage-draft-1",
        wardId: 12,
        wardPublicId: "ward-public-1",
        diarrhea: true,
        vomiting: true,
        dehydration: false,
        fever: false,
        textInput: "Loose stool and vomiting",
      },
      baseNow,
    );
    store = upsertPreventionVisitDraft(
      store,
      {
        draftId: "prevention-draft-1",
        taskPublicId: "task-public-1",
        visitCompleted: true,
        householdsReachedCount: 4,
        messagesDeliveredCount: 4,
        waterTreatmentDemo: true,
      },
      baseNow,
    );
    store = queueChvPendingSyncItem(
      store,
      {
        localId: "sync-1",
        clientSubmissionId: "client-1",
        idempotencyKey: "idem-1",
        uploadType: "symptom_triage",
        draftLocalId: "triage-draft-1",
        payload: {
          diarrhea: true,
          vomiting: true,
          dehydration: false,
          fever: false,
          text_input: "Loose stool and vomiting",
        },
      },
      baseNow,
    );

    expect(store.symptomTriageDrafts[0]).toMatchObject({
      schemaVersion: CHV_OFFLINE_LOCAL_SCHEMA_VERSION,
      localId: "triage-draft-1",
      draftType: "symptom_triage",
      requestedLanguage: "sw",
      resolvedLanguage: "en",
      fallbackUsed: true,
      wardId: 12,
    });
    expect(store.preventionVisitDrafts[0]).toMatchObject({
      schemaVersion: CHV_OFFLINE_LOCAL_SCHEMA_VERSION,
      draftType: "prevention_visit",
      requestedLanguage: "sw",
      resolvedLanguage: "en",
      fallbackUsed: true,
      householdsReachedCount: 4,
    });
    expect(store.pendingSyncItems[0]).toMatchObject({
      schemaVersion: CHV_OFFLINE_LOCAL_SCHEMA_VERSION,
      clientSubmissionId: "client-1",
      idempotencyKey: "idem-1",
      uploadType: "symptom_triage",
      requestedLanguage: "sw",
      resolvedLanguage: "en",
      fallbackUsed: true,
      downloadBundleVersion: "chv-bundle-phase2",
    });

    store = setChvOfflineSelectedLanguage(store, "luo", baseNow);
    expect(store.pendingSyncItems[0]).toMatchObject({
      requestedLanguage: "sw",
      resolvedLanguage: "en",
      fallbackUsed: true,
    });
    expect(JSON.stringify(store)).not.toContain("household_name");
    expect(JSON.stringify(store)).not.toContain("caregiver_name");
  });

  it("tracks failed syncs, conflicts, and last-success metadata", () => {
    let store = createEmptyChvOfflineStore(scopeKey, baseNow);
    store = queueChvPendingSyncItem(
      store,
      {
        localId: "sync-1",
        clientSubmissionId: "client-1",
        idempotencyKey: "idem-1",
        uploadType: "symptom_triage",
        payload: { diarrhea: true },
      },
      baseNow,
    );
    store = movePendingSyncItemToFailed(
      store,
      "sync-1",
      { failureReason: "Network unavailable", serverStatus: null },
      new Date("2026-05-04T09:00:00.000Z"),
    );
    store = recordChvSyncConflict(
      store,
      {
        clientSubmissionId: "client-2",
        idempotencyKey: "idem-2",
        uploadType: "symptom_triage",
        conflictState: "REPLAYED",
        serverReceipt: { receipt_id: "sync-12" },
      },
      new Date("2026-05-04T10:00:00.000Z"),
    );
    store = queueChvPendingSyncItem(
      store,
      {
        localId: "sync-3",
        clientSubmissionId: "client-3",
        idempotencyKey: "idem-3",
        uploadType: "suspected_case_signal",
        payload: { diarrhea: true, dehydration: true },
      },
      new Date("2026-05-04T11:00:00.000Z"),
    );
    store = markChvSyncItemSent(
      store,
      "sync-3",
      {
        contractVersion: "chv-offline-v1",
        deviceRegistrationId: "device-registration-public-1",
        sourceDeviceId: "field-device-1",
        downloadBundleVersion: "chv-bundle-phase2",
        lastSuccessfulSyncAt: "2026-05-04T11:05:00.000Z",
        requestedLanguage: "en",
        resolvedLanguage: "en",
        fallbackUsed: false,
        pendingUploadCount: 0,
        failedUploadCount: 1,
        syncHealth: "ONLINE",
      },
      new Date("2026-05-04T11:05:00.000Z"),
    );

    expect(store.pendingSyncItems).toHaveLength(0);
    expect(store.failedSyncItems).toHaveLength(1);
    expect(store.failedSyncItems[0]).toMatchObject({
      clientSubmissionId: "client-1",
      failureReason: "Network unavailable",
    });
    expect(store.conflictItems[0]).toMatchObject({
      conflictState: "REPLAYED",
      resolutionStatus: "UNRESOLVED",
    });
    expect(store.lastSuccessfulSync).toMatchObject({
      schemaVersion: CHV_OFFLINE_LOCAL_SCHEMA_VERSION,
      syncHealth: "ONLINE",
      failedUploadCount: 1,
    });
  });

  it("keeps retryable sync attempts pending with attempt metadata", () => {
    let store = createEmptyChvOfflineStore(scopeKey, baseNow);
    store = queueChvPendingSyncItem(
      store,
      {
        localId: "retry-sync-1",
        clientSubmissionId: "retry-client-1",
        idempotencyKey: "retry-idem-1",
        uploadType: "symptom_triage",
        payload: { diarrhea: true },
      },
      baseNow,
    );

    store = markChvPendingSyncItemAttempted(
      store,
      "retry-sync-1",
      new Date("2026-05-04T09:15:00.000Z"),
    );

    expect(store.pendingSyncItems).toHaveLength(1);
    expect(store.pendingSyncItems[0]).toMatchObject({
      localId: "retry-sync-1",
      status: "PENDING",
      attemptCount: 1,
      lastAttemptAt: "2026-05-04T09:15:00.000Z",
      updatedAt: "2026-05-04T09:15:00.000Z",
    });
    expect(store.failedSyncItems).toEqual([]);
  });

  it("purges sensitive local entities according to retention rules", () => {
    const oldNow = new Date("2026-05-01T08:00:00.000Z");
    let store = createEmptyChvOfflineStore(scopeKey, oldNow);
    store = cacheChvOfflineDownloadBundle(store, bundle({ expires_at: "2026-05-01T20:00:00.000Z" }), "chv-offline-v1", oldNow);
    store = upsertSymptomTriageDraft(
      store,
      {
        draftId: "triage-old",
        wardId: 12,
        wardPublicId: "ward-public-1",
        textInput: "Loose stool",
      },
      oldNow,
    );
    store = upsertPreventionVisitDraft(
      store,
      { draftId: "prevention-old", taskPublicId: "task-public-1", householdsReachedCount: 2 },
      oldNow,
    );
    store = queueChvPendingSyncItem(
      store,
      {
        localId: "pending-old",
        clientSubmissionId: "pending-old",
        idempotencyKey: "pending-old",
        uploadType: "symptom_triage",
        payload: { diarrhea: true },
      },
      oldNow,
    );
    store = movePendingSyncItemToFailed(
      store,
      "pending-old",
      { failureReason: "Timeout", serverStatus: 504 },
      oldNow,
    );
    store = recordChvSyncConflict(
      store,
      {
        clientSubmissionId: "client-conflict",
        idempotencyKey: "idem-conflict",
        uploadType: "symptom_triage",
        conflictState: "REPLAYED",
      },
      oldNow,
    );

    const purged = applyChvOfflineRetentionRules(
      store,
      new Date(oldNow.getTime() + (CHV_OFFLINE_RETENTION_RULES.failedSyncItemDays + 1) * 24 * 60 * 60 * 1000),
    );

    expect(purged.wardGuidance).toEqual([]);
    expect(purged.symptomTriageDrafts).toEqual([]);
    expect(purged.preventionVisitDrafts).toEqual([]);
    expect(purged.failedSyncItems).toEqual([]);
    expect(purged.conflictItems).toEqual([]);
    expect(isChvOfflineBundleStale(purged, new Date("2026-05-10T08:00:00.000Z"))).toBe(true);
  });
});
