"use client";

import {
  AlertTriangle,
  BookOpen,
  CheckCircle2,
  ClipboardCheck,
  ClipboardList,
  Cloud,
  CloudOff,
  FileWarning,
  HeartPulse,
  Languages,
  Loader2,
  MapPin,
  Monitor,
  Moon,
  RefreshCw,
  Send,
  ShieldCheck,
  Sun,
  Thermometer,
  UserRound,
  Wifi,
  WifiOff,
  XCircle,
  type LucideIcon,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { Button } from "@/components/ui/button";
import { PublicCard, PublicScreen } from "@/components/ui/public-shell";
import type { CurrentUser, ThemePreference } from "@/lib/auth";
import {
  CHV_LANGUAGE_OPTIONS,
  chvTranslate,
  normalizeChvLanguage,
  type ChvSupportedLanguage,
  type ChvUiTranslationKey,
} from "@/lib/chv-localization";
import {
  buildChvOfflineSyncRequest,
  fetchChvOfflineContractViaBff,
  getOrCreateChvOfflineDeviceId,
  getStoredChvOfflineDeviceRegistrationId,
  isChvOfflineUploadSyncable,
  postChvOfflineSyncViaBff,
  postChvDeviceRegistrationViaBff,
  storeChvOfflineDeviceRegistrationId,
  type ChvOfflineSyncResult,
} from "@/lib/chv-offline-api";
import {
  applyChvOfflineRetentionRules,
  cacheChvOfflineDownloadBundle,
  describeChvOfflineBundleFreshness,
  markChvOfflineCachedBundleLanguageFallback,
  markChvAssignedTaskStatus,
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
  type ChvOfflineAssignedTask,
  type ChvOfflineDecisionSupportRecommendation,
  type ChvOfflineDownloadBundleInput,
  type ChvOfflineLocalStore,
  type ChvOfflineUploadType,
} from "@/lib/chv-offline-store";
import { cn } from "@/lib/cn";
import { canUseChvOffline } from "@/lib/roles";

type ChvView = "tasks" | "triage" | "guidance" | "sync" | "profile";

type TriageState = {
  diarrhea: boolean;
  vomiting: boolean;
  dehydration: boolean;
  fever: boolean;
  textInput: string;
};

type DecisionSupportRecommendationKey =
  | "urgent_referral"
  | "facility_assessment"
  | "ors_and_prevention"
  | "record_symptoms";

type DecisionSupportRecommendationTone = "urgent" | "warning" | "advice" | "neutral";

type PreventionVisitState = {
  householdsReachedCount: number;
  messagesDeliveredCount: number;
  waterTreatmentDemo: boolean;
  soapOrHandwashingDiscussed: boolean;
};

type SymptomOption = {
  field: Exclude<keyof TriageState, "textInput">;
  labelKey: ChvUiTranslationKey;
  icon: LucideIcon;
};

type ChvStatusKey =
  | "online"
  | "offline"
  | "clear"
  | "sent"
  | "pending"
  | "rejected"
  | "assigned"
  | "stale"
  | "ready"
  | "unavailable";
type ChvPageTranslator = (key: ChvUiTranslationKey, values?: Record<string, string | number>) => string;

const defaultT: ChvPageTranslator = (key, values) => chvTranslate("en", key, values);

const EMPTY_TRIAGE: TriageState = {
  diarrhea: false,
  vomiting: false,
  dehydration: false,
  fever: false,
  textInput: "",
};

const EMPTY_PREVENTION_VISIT: PreventionVisitState = {
  householdsReachedCount: 1,
  messagesDeliveredCount: 1,
  waterTreatmentDemo: false,
  soapOrHandwashingDiscussed: false,
};

const DECISION_SUPPORT_RECOMMENDATION_TEMPLATE_KEYS: Record<DecisionSupportRecommendationKey, string> = {
  urgent_referral: "cholera.chv.triage.urgent_referral_offline",
  facility_assessment: "cholera.chv.triage.facility_assessment_offline",
  ors_and_prevention: "cholera.chv.triage.ors_and_prevention_offline",
  record_symptoms: "cholera.chv.triage.record_symptoms_offline",
};

const VIEWS: Array<{ id: ChvView; labelKey: ChvUiTranslationKey; icon: LucideIcon }> = [
  { id: "tasks", labelKey: "nav.tasks", icon: ClipboardList },
  { id: "triage", labelKey: "nav.triage", icon: HeartPulse },
  { id: "guidance", labelKey: "nav.guidance", icon: BookOpen },
  { id: "sync", labelKey: "nav.sync", icon: Cloud },
  { id: "profile", labelKey: "nav.profile", icon: UserRound },
];

const APPEARANCE_OPTIONS: Array<{ value: ThemePreference; labelKey: ChvUiTranslationKey; icon: LucideIcon }> = [
  { value: "LIGHT", labelKey: "appearance.light", icon: Sun },
  { value: "SYSTEM", labelKey: "appearance.system", icon: Monitor },
  { value: "DARK", labelKey: "appearance.dark", icon: Moon },
];

const SYMPTOM_OPTIONS: SymptomOption[] = [
  { field: "diarrhea", labelKey: "triage.diarrhea", icon: HeartPulse },
  { field: "vomiting", labelKey: "triage.vomiting", icon: AlertTriangle },
  { field: "dehydration", labelKey: "triage.dehydration", icon: ShieldCheck },
  { field: "fever", labelKey: "triage.fever", icon: Thermometer },
];

function addHours(now: Date, hours: number) {
  return new Date(now.getTime() + hours * 60 * 60 * 1000).toISOString();
}

function buildScopeKey(user: CurrentUser) {
  const wardPart = user.ward ? `ward-${user.ward}` : "ward-unassigned";
  return `${wardPart}.user-${user.id}`;
}

function buildFallbackBundle(
  user: CurrentUser,
  now: Date,
  requestedLanguage: ChvSupportedLanguage = "en",
): ChvOfflineDownloadBundleInput {
  const wardId = user.ward ?? 0;
  const wardPublicId = `local-ward-${wardId || user.id}`;
  const fallbackUsed = requestedLanguage !== "en";

  return {
    version: `chv-bundle-local-phase3-${wardId || user.id}`,
    generated_at: now.toISOString(),
    expires_at: addHours(now, 24),
    requested_language: requestedLanguage,
    resolved_language: "en",
    fallback_used: fallbackUsed,
    task_bundle: {
      schema_version: "chv-task-bundle-v1",
      tasks: [
        {
          task_public_id: `local-follow-up-${wardId || user.id}`,
          task_type: "preparedness_action",
          action_type: "CHV_FOLLOW_UP",
          status: "ASSIGNED",
          priority: "HIGH",
          ward_id: wardId,
          ward_public_id: wardPublicId,
          due_at: addHours(now, 4),
          allowed_upload_types: ["symptom_triage", "suspected_case_signal"],
          minimum_capture: ["symptoms", "ward", "recorded time"],
        },
      ],
    },
    guidance_bundle: {
      schema_version: "chv-guidance-bundle-v1",
      requested_language: requestedLanguage,
      resolved_language: "en",
      fallback_used: fallbackUsed,
      content_unavailable: true,
      governance_status: "local_fallback_requires_live_governed_bundle",
      items: [],
    },
    decision_support_rule_bundle: {
      version: "cholera-triage-rules-v1",
      requested_language: requestedLanguage,
      resolved_language: "en",
      fallback_used: fallbackUsed,
      content_unavailable: true,
      governance_status: "local_fallback_requires_live_governed_bundle",
      missing_recommendation_keys: [
        "urgent_referral",
        "facility_assessment",
        "ors_and_prevention",
        "record_symptoms",
      ],
      recommendations: [],
    },
  };
}

function formatShortDate(value: string | null | undefined, language: ChvSupportedLanguage = "en") {
  if (!value) {
    return chvTranslate(language, "date.notSet");
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return chvTranslate(language, "date.notSet");
  }

  const locale = language === "sw" ? "sw-KE" : language === "luo" ? "luo-KE" : "en-KE";
  return new Intl.DateTimeFormat(locale, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function titleFromTask(task: ChvOfflineAssignedTask, t: ChvPageTranslator = defaultT) {
  if ((task.actionType ?? "").toUpperCase() === "CHV_FOLLOW_UP") {
    return t("task.householdFollowUp");
  }
  if (task.taskType === "chv_coverage_assignment") {
    return t("task.coverageFollowUp");
  }
  return t("task.wardFollowUp");
}

function uploadTypeLabel(uploadType: ChvOfflineUploadType, t: ChvPageTranslator = defaultT) {
  switch (uploadType) {
    case "prevention_visit":
      return t("upload.prevention_visit");
    case "task_ack":
      return t("upload.task_ack");
    case "alert_ack":
      return t("upload.alert_ack");
    case "suspected_case_signal":
      return t("upload.suspected_case_signal");
    case "symptom_triage":
    default:
      return t("upload.symptom_triage");
  }
}

function conflictLabel(conflictState: string, t: ChvPageTranslator = defaultT) {
  const key = `conflict.${conflictState}` as ChvUiTranslationKey;
  return t(key);
}

function taskStatus(store: ChvOfflineLocalStore, task: ChvOfflineAssignedTask): ChvStatusKey {
  const hasFailed = store.failedSyncItems.some((item) => item.payload.task_public_id === task.taskPublicId);
  if (hasFailed) {
    return "rejected";
  }

  const hasPending = store.pendingSyncItems.some((item) => item.payload.task_public_id === task.taskPublicId);
  if (hasPending || task.status === "PENDING_SYNC") {
    return "pending";
  }

  if (task.status === "SENT") {
    return "sent";
  }

  return "assigned";
}

function statusClasses(status: ChvStatusKey) {
  if (status === "online" || status === "clear" || status === "ready" || status === "sent") {
    return "border-[color-mix(in_srgb,var(--success)_28%,transparent)] bg-[color-mix(in_srgb,var(--success)_12%,transparent)] text-[color:var(--success)]";
  }
  if (status === "offline" || status === "pending" || status === "stale") {
    return "border-[color-mix(in_srgb,var(--warning)_30%,transparent)] bg-[color-mix(in_srgb,var(--warning)_12%,transparent)] text-[color:var(--warning)]";
  }
  if (status === "rejected" || status === "unavailable") {
    return "border-[color-mix(in_srgb,var(--danger)_30%,transparent)] bg-[color-mix(in_srgb,var(--danger)_12%,transparent)] text-[color:var(--danger)]";
  }
  return "border-panel-table-wrap bg-[color-mix(in_srgb,var(--dashboard-table-line)_24%,transparent)] text-panel-copy";
}

function StatusBadge({ status, label }: { status: ChvStatusKey; label: string }) {
  return (
    <span className={`inline-flex min-h-7 items-center rounded-md border px-2.5 text-xs font-semibold ${statusClasses(status)}`}>
      {label}
    </span>
  );
}

function statusLabel(status: ChvStatusKey, t: ChvPageTranslator) {
  return t(`status.${status}` as ChvUiTranslationKey);
}

function recommendationDecision(triage: TriageState): {
  key: DecisionSupportRecommendationKey;
  tone: DecisionSupportRecommendationTone;
} {
  if (triage.dehydration && (triage.diarrhea || triage.vomiting)) {
    return { key: "urgent_referral", tone: "urgent" };
  }
  if (triage.diarrhea && (triage.vomiting || triage.fever)) {
    return { key: "facility_assessment", tone: "warning" };
  }
  if (triage.diarrhea) {
    return { key: "ors_and_prevention", tone: "advice" };
  }
  return { key: "record_symptoms", tone: "neutral" };
}

function recommendationFor(
  triage: TriageState,
  recommendations: ChvOfflineDecisionSupportRecommendation[],
  t: ChvPageTranslator = defaultT,
) {
  const decision = recommendationDecision(triage);
  const governedRecommendation = recommendations.find(
    (recommendation) => recommendation.recommendationKey === decision.key,
  );
  if (!governedRecommendation) {
    return {
      key: decision.key,
      templateKey: DECISION_SUPPORT_RECOMMENDATION_TEMPLATE_KEYS[decision.key],
      tone: decision.tone,
      title: t("triage.recommendationUnavailableTitle"),
      body: t("triage.recommendationUnavailableBody"),
      fallbackUsed: false,
      contentUnavailable: true,
      governanceStatus: "unavailable",
    };
  }
  return {
    key: decision.key,
    templateKey: governedRecommendation.templateKey,
    tone: decision.tone,
    title: governedRecommendation.title,
    body: governedRecommendation.body,
    fallbackUsed: governedRecommendation.fallbackUsed,
    contentUnavailable: false,
    governanceStatus: governedRecommendation.governanceStatus,
  };
}

function safeSyncErrorMessage(_error: unknown, fallbackMessage: string) {
  return fallbackMessage;
}

function errorStatus(error: unknown) {
  if (error && typeof error === "object" && "status" in error && typeof error.status === "number") {
    return error.status;
  }
  return null;
}

function isRetryableSyncError(error: unknown) {
  const status = errorStatus(error);
  return status === null || status >= 500;
}

function findResultForItem(results: ChvOfflineSyncResult[], idempotencyKey: string) {
  return results.find((result) => result.idempotency_key === idempotencyKey);
}

function ChvOfflineWorkspace({ currentUser }: { currentUser: CurrentUser }) {
  const { updateAppearance } = useAuth();
  const [store, setStore] = useState<ChvOfflineLocalStore | null>(null);
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [activeView, setActiveView] = useState<ChvView>("tasks");
  const [triage, setTriage] = useState<TriageState>(EMPTY_TRIAGE);
  const [preventionVisit, setPreventionVisit] = useState<PreventionVisitState>(EMPTY_PREVENTION_VISIT);
  const [deviceId, setDeviceId] = useState("");
  const [deviceRegistrationId, setDeviceRegistrationId] = useState("");
  const [isOnline, setIsOnline] = useState(() => (typeof navigator === "undefined" ? true : navigator.onLine));
  const [syncMessage, setSyncMessage] = useState<string | null>(null);
  const [isSyncing, setIsSyncing] = useState(false);
  const [isChangingLanguage, setIsChangingLanguage] = useState(false);
  const [appearancePreference, setAppearancePreference] = useState<ThemePreference>(currentUser.theme_preference);
  const [isChangingAppearance, setIsChangingAppearance] = useState(false);
  const selectedLanguage = store?.selectedLanguage ?? "en";
  const t = useCallback<ChvPageTranslator>(
    (key, values) => chvTranslate(selectedLanguage, key, values),
    [selectedLanguage],
  );
  const canUpdateAppearance = currentUser.profile_capabilities?.can_update_appearance ?? currentUser.is_active;

  const persistStore = useCallback((nextStore: ChvOfflineLocalStore) => {
    writeChvOfflineStore(nextStore);
    setStore(nextStore);
  }, []);

  useEffect(() => {
    setAppearancePreference(currentUser.theme_preference);
  }, [currentUser.theme_preference]);

  useEffect(() => {
    let isCancelled = false;
    const nextDeviceId = getOrCreateChvOfflineDeviceId();
    setDeviceId(nextDeviceId);
    setDeviceRegistrationId(getStoredChvOfflineDeviceRegistrationId());

    const now = new Date();
    const scopeKey = buildScopeKey(currentUser);
    const stored = applyChvOfflineRetentionRules(readChvOfflineStore(scopeKey, undefined, now), now);
    const preferredLanguage = stored.selectedLanguage;
    const initialized =
      stored.bundleMetadata || typeof currentUser.ward !== "number"
        ? stored
        : cacheChvOfflineDownloadBundle(stored, buildFallbackBundle(currentUser, now, preferredLanguage), undefined, now);

    persistStore(initialized);
    setSelectedTaskId((existing) => existing ?? initialized.assignedTasks[0]?.taskPublicId ?? null);

    if (!isOnline || typeof currentUser.ward !== "number") {
      return () => {
        isCancelled = true;
      };
    }

    async function loadLiveOfflineContract() {
      try {
        const [contract, registration] = await Promise.all([
          fetchChvOfflineContractViaBff({
            language: preferredLanguage,
            deviceRegistrationId: getStoredChvOfflineDeviceRegistrationId(),
          }),
          postChvDeviceRegistrationViaBff({
            device_id: nextDeviceId,
            contract_version: "chv-offline-v1",
            platform: "WEB",
            preferred_language: preferredLanguage,
          }),
        ]);

        if (isCancelled) {
          return;
        }

        const refreshedAt = new Date();
        const latestLocalStore = applyChvOfflineRetentionRules(
          readChvOfflineStore(scopeKey, undefined, refreshedAt),
          refreshedAt,
        );
        const liveStore = cacheChvOfflineDownloadBundle(
          latestLocalStore,
          contract.download_bundle,
          contract.contract_version,
          refreshedAt,
        );
        persistStore(liveStore);
        setDeviceRegistrationId(storeChvOfflineDeviceRegistrationId(registration.public_id));
        setSelectedTaskId((existing) => existing ?? liveStore.assignedTasks[0]?.taskPublicId ?? null);
      } catch {
        if (!isCancelled && !initialized.bundleMetadata) {
          setSyncMessage(chvTranslate(preferredLanguage, "message.localFallbackBundle"));
        }
      }
    }

    void loadLiveOfflineContract();

    return () => {
      isCancelled = true;
    };
  }, [currentUser, isOnline, persistStore]);

  useEffect(() => {
    function handleOnline() {
      setIsOnline(true);
    }
    function handleOffline() {
      setIsOnline(false);
    }

    window.addEventListener("online", handleOnline);
    window.addEventListener("offline", handleOffline);
    return () => {
      window.removeEventListener("online", handleOnline);
      window.removeEventListener("offline", handleOffline);
    };
  }, []);

  useEffect(() => {
    setTriage(EMPTY_TRIAGE);
    setPreventionVisit(EMPTY_PREVENTION_VISIT);
  }, [selectedTaskId]);

  const selectedTask = useMemo(() => {
    if (!store) {
      return null;
    }
    return store.assignedTasks.find((task) => task.taskPublicId === selectedTaskId) ?? store.assignedTasks[0] ?? null;
  }, [selectedTaskId, store]);

  const bundleFreshness = store ? describeChvOfflineBundleFreshness(store) : null;
  const pendingCount = store?.pendingSyncItems.length ?? 0;
  const rejectedCount = store?.failedSyncItems.length ?? 0;
  const conflictCount = store?.conflictItems.filter((item) => item.resolutionStatus === "UNRESOLVED").length ?? 0;
  const hasSymptoms = triage.diarrhea || triage.vomiting || triage.dehydration || triage.fever;
  const bundleContentUnavailable = Boolean(
    store?.bundleMetadata?.guidanceContentUnavailable
      || store?.bundleMetadata?.decisionSupportContentUnavailable,
  );
  const recommendation = recommendationFor(triage, store?.decisionSupportRecommendations ?? [], t);

  function updateTriageField(field: keyof TriageState, value: boolean | string) {
    setTriage((current) => ({ ...current, [field]: value }));
  }

  function handleSaveTriage() {
    if (!store || !selectedTask || !hasSymptoms) {
      setSyncMessage(t("message.selectSymptom"));
      return;
    }

    const now = new Date();
    const draftId = `triage-${selectedTask.taskPublicId}-${now.getTime()}`;
    let nextStore = upsertSymptomTriageDraft(
      store,
      {
        draftId,
        wardId: selectedTask.wardId,
        wardPublicId: selectedTask.wardPublicId,
        diarrhea: triage.diarrhea,
        vomiting: triage.vomiting,
        dehydration: triage.dehydration,
        fever: triage.fever,
        textInput: triage.textInput.trim(),
      },
      now,
    );

    nextStore = queueChvPendingSyncItem(
      nextStore,
      {
        uploadType: "symptom_triage",
        payload: {
          task_public_id: selectedTask.taskPublicId,
          ward_id: selectedTask.wardId,
          ward_public_id: selectedTask.wardPublicId,
          diarrhea: triage.diarrhea,
          vomiting: triage.vomiting,
          dehydration: triage.dehydration,
          fever: triage.fever,
          text_input: triage.textInput.trim(),
        },
        draftLocalId: draftId,
      },
      now,
    );
    nextStore = markChvAssignedTaskStatus(nextStore, selectedTask.taskPublicId, "PENDING_SYNC", now);

    persistStore(nextStore);
    setTriage(EMPTY_TRIAGE);
    setActiveView("sync");
    setSyncMessage(t("message.followUpSaved"));
  }

  function handleAcknowledgeTask() {
    if (!store || !selectedTask) {
      return;
    }
    if (selectedTask.taskType !== "preparedness_action" || !selectedTask.allowedUploadTypes.includes("task_ack")) {
      setSyncMessage(t("message.taskCannotAck"));
      return;
    }

    const now = new Date();
    let nextStore = queueChvPendingSyncItem(
      store,
      {
        uploadType: "task_ack",
        payload: {
          task_public_id: selectedTask.taskPublicId,
          action_public_id: selectedTask.taskPublicId,
          acknowledgment_status: "ACKNOWLEDGED",
          coded_reason: "field_follow_up_started",
        },
      },
      now,
    );
    nextStore = markChvAssignedTaskStatus(nextStore, selectedTask.taskPublicId, "PENDING_SYNC", now);
    persistStore(nextStore);
    setActiveView("sync");
    setSyncMessage(t("message.taskAckSaved"));
  }

  function updatePreventionVisitField(field: keyof PreventionVisitState, value: boolean | number) {
    setPreventionVisit((current) => ({ ...current, [field]: value }));
  }

  function handleSavePreventionVisit() {
    if (!store || !selectedTask) {
      return;
    }
    if (selectedTask.taskType !== "preparedness_action" || !selectedTask.allowedUploadTypes.includes("prevention_visit")) {
      setSyncMessage(t("message.taskCannotPrevention"));
      return;
    }

    const now = new Date();
    const householdsReachedCount = Math.max(0, preventionVisit.householdsReachedCount);
    const messagesDeliveredCount = Math.max(0, preventionVisit.messagesDeliveredCount);
    const draftId = `prevention-${selectedTask.taskPublicId}-${now.getTime()}`;
    let nextStore = upsertPreventionVisitDraft(
      store,
      {
        draftId,
        taskPublicId: selectedTask.taskPublicId,
        actionPublicId: selectedTask.taskPublicId,
        visitCompleted: true,
        householdsReachedCount,
        messagesDeliveredCount,
        waterTreatmentDemo: preventionVisit.waterTreatmentDemo,
        soapOrHandwashingDiscussed: preventionVisit.soapOrHandwashingDiscussed,
      },
      now,
    );
    nextStore = queueChvPendingSyncItem(
      nextStore,
      {
        uploadType: "prevention_visit",
        payload: {
          task_public_id: selectedTask.taskPublicId,
          action_public_id: selectedTask.taskPublicId,
          visit_completed: true,
          households_reached_count: householdsReachedCount,
          messages_delivered_count: messagesDeliveredCount,
          water_treatment_demo: preventionVisit.waterTreatmentDemo,
          soap_or_handwashing_discussed: preventionVisit.soapOrHandwashingDiscussed,
        },
        draftLocalId: draftId,
      },
      now,
    );
    nextStore = markChvAssignedTaskStatus(nextStore, selectedTask.taskPublicId, "PENDING_SYNC", now);
    persistStore(nextStore);
    setPreventionVisit(EMPTY_PREVENTION_VISIT);
    setActiveView("sync");
    setSyncMessage(t("message.preventionSaved"));
  }

  async function handleSyncNow() {
    if (!store) {
      return;
    }
    if (!isOnline) {
      setSyncMessage(t("message.offlinePending"));
      return;
    }

    const syncableItems = store.pendingSyncItems.filter((item) => isChvOfflineUploadSyncable(item.uploadType));
    if (syncableItems.length === 0) {
      setSyncMessage(t("message.noPendingWork"));
      return;
    }

    setIsSyncing(true);
    setSyncMessage(null);

    let nextStore = store;
    let sentCount = 0;
    let rejectedCountInRun = 0;
    let retryLaterCount = 0;
    let lastFailureMessage = "";

    try {
      for (const item of syncableItems) {
        try {
          const request = buildChvOfflineSyncRequest(nextStore, currentUser, [item], deviceId, deviceRegistrationId);
          const response = await postChvOfflineSyncViaBff(request);
          const now = new Date();
          const result = findResultForItem(response.results, item.idempotencyKey);
          const lastSuccessfulSyncAt = response.sync_health_record.last_successful_sync_at ?? now.toISOString();
          nextStore = markChvSyncItemSent(
            nextStore,
            item.localId,
            {
              contractVersion: response.contract_version,
              deviceRegistrationId,
              sourceDeviceId: deviceId,
              downloadBundleVersion: item.downloadBundleVersion || nextStore.bundleMetadata?.downloadBundleVersion || "",
              lastSuccessfulSyncAt,
              requestedLanguage: response.requested_language ?? nextStore.bundleMetadata?.requestedLanguage ?? "en",
              resolvedLanguage: response.resolved_language ?? nextStore.bundleMetadata?.resolvedLanguage ?? "en",
              fallbackUsed: Boolean(response.fallback_used ?? nextStore.bundleMetadata?.fallbackUsed ?? false),
              pendingUploadCount: response.sync_health_record.pending_upload_count,
              failedUploadCount: response.sync_health_record.failed_upload_count,
              syncHealth: response.sync_health_record.sync_health,
            },
            now,
          );

          if (typeof item.payload.task_public_id === "string") {
            nextStore = markChvAssignedTaskStatus(nextStore, item.payload.task_public_id, "SENT", now);
          }

          if (result && result.conflict_state !== "NONE") {
            nextStore = recordChvSyncConflict(
              nextStore,
              {
                clientSubmissionId: result.client_submission_id,
                idempotencyKey: result.idempotency_key,
                uploadType: result.upload_type,
                conflictState: result.conflict_state === "REPLAYED" ? "REPLAYED" : "STALE_BUNDLE",
                serverReceipt: result.server_receipt,
                resolutionStatus: result.conflict_state === "REPLAYED" ? "RESOLVED" : "UNRESOLVED",
              },
              now,
            );
          }
          sentCount += 1;
        } catch (error) {
          const now = new Date();
          const message = safeSyncErrorMessage(error, t("message.syncError"));
          lastFailureMessage = message;
          if (isRetryableSyncError(error)) {
            retryLaterCount += 1;
            nextStore = markChvPendingSyncItemAttempted(nextStore, item.localId, now);
            break;
          } else {
            rejectedCountInRun += 1;
            nextStore = movePendingSyncItemToFailed(
              nextStore,
              item.localId,
              {
                failureReason: message,
                serverStatus: errorStatus(error),
              },
              now,
            );
            if (typeof item.payload.task_public_id === "string") {
              nextStore = markChvAssignedTaskStatus(nextStore, item.payload.task_public_id, "REJECTED", now);
            }
          }
        }
      }

      persistStore(nextStore);
      if (retryLaterCount > 0) {
        const syncParts = [t("sync.countSent", { count: sentCount })];
        if (rejectedCountInRun > 0) {
          syncParts.push(t("sync.countRejected", { count: rejectedCountInRun }));
        }
        syncParts.push(t("sync.countRetry", { count: retryLaterCount }));
        setSyncMessage(`${syncParts.join(", ")}. ${lastFailureMessage}`);
      } else {
        setSyncMessage(
          rejectedCountInRun
            ? `${t("sync.countSent", { count: sentCount })}, ${t("sync.countRejected", { count: rejectedCountInRun })}. ${lastFailureMessage}`
            : t("message.sent"),
        );
      }
    } catch (error) {
      persistStore(nextStore);
      setSyncMessage(safeSyncErrorMessage(error, t("message.syncError")));
    } finally {
      setIsSyncing(false);
    }
  }

  function dismissConflict(localId: string) {
    if (!store) {
      return;
    }

    persistStore({
      ...store,
      conflictItems: store.conflictItems.map((item) =>
        item.localId === localId ? { ...item, resolutionStatus: "DISMISSED" } : item,
      ),
    });
  }

  async function handleLanguageChange(language: string) {
    if (!store) {
      return;
    }
    const nextLanguage = normalizeChvLanguage(language);
    const now = new Date();
    const scopeKey = store.scopeKey;
    const offlineLanguageMessage = chvTranslate(nextLanguage, "message.languageSavedOffline");
    let nextStore = setChvOfflineSelectedLanguage(store, nextLanguage, now);

    if (!isOnline || typeof currentUser.ward !== "number") {
      if (!nextStore.bundleMetadata || nextStore.bundleMetadata.downloadBundleVersion.startsWith("chv-bundle-local-phase3")) {
        nextStore = cacheChvOfflineDownloadBundle(
          nextStore,
          buildFallbackBundle(currentUser, now, nextLanguage),
          nextStore.bundleMetadata?.contractVersion,
          now,
        );
      } else {
        nextStore = markChvOfflineCachedBundleLanguageFallback(nextStore, nextLanguage, now);
      }
      persistStore(nextStore);
      setSyncMessage(offlineLanguageMessage);
      return;
    }

    persistStore(nextStore);
    setIsChangingLanguage(true);
    try {
      const contract = await fetchChvOfflineContractViaBff({
        language: nextLanguage,
        deviceRegistrationId: getStoredChvOfflineDeviceRegistrationId(),
      });
      const registration = await postChvDeviceRegistrationViaBff({
        device_id: deviceId || getOrCreateChvOfflineDeviceId(),
        contract_version: "chv-offline-v1",
        platform: "WEB",
        preferred_language: nextLanguage,
      });
      const refreshedAt = new Date();
      const latestLocalStore = setChvOfflineSelectedLanguage(
        applyChvOfflineRetentionRules(readChvOfflineStore(scopeKey, undefined, refreshedAt), refreshedAt),
        nextLanguage,
        refreshedAt,
      );
      const liveStore = cacheChvOfflineDownloadBundle(
        latestLocalStore,
        contract.download_bundle,
        contract.contract_version,
        refreshedAt,
      );
      persistStore(liveStore);
      setDeviceRegistrationId(storeChvOfflineDeviceRegistrationId(registration.public_id));
      setSelectedTaskId((existing) => existing ?? liveStore.assignedTasks[0]?.taskPublicId ?? null);
      setSyncMessage(
        contract.fallback_used || contract.download_bundle.fallback_used
          ? chvTranslate(nextLanguage, "message.languageFallback")
          : chvTranslate(nextLanguage, "message.languageUpdated"),
      );
    } catch {
      persistStore(markChvOfflineCachedBundleLanguageFallback(readChvOfflineStore(scopeKey), nextLanguage, new Date()));
      setSyncMessage(offlineLanguageMessage);
    } finally {
      setIsChangingLanguage(false);
    }
  }

  async function handleAppearanceChange(themePreference: ThemePreference) {
    if (!canUpdateAppearance || isChangingAppearance || themePreference === appearancePreference) {
      return;
    }

    const previousPreference = appearancePreference;
    setAppearancePreference(themePreference);
    setIsChangingAppearance(true);

    try {
      await updateAppearance(themePreference);
    } catch (error) {
      console.error("Unable to update CHV appearance preference", error);
      setAppearancePreference(previousPreference);
    } finally {
      setIsChangingAppearance(false);
    }
  }

  if (!store) {
    return (
      <PublicScreen className="min-h-screen bg-app-bg-fade text-panel-strong">
        <div className="flex min-h-screen items-center justify-center">
          <div className="inline-flex items-center gap-3 text-sm font-semibold text-panel-copy">
            <Loader2 className="size-5 animate-spin" aria-hidden="true" />
            {t("app.loadingWorkspace")}
          </div>
        </div>
      </PublicScreen>
    );
  }

  return (
    <main className="min-h-screen bg-app-bg-fade text-panel-strong">
      <header className="sticky top-0 z-20 border-b border-[var(--dashboard-topbar-border)] bg-[var(--dashboard-topbar-surface)] backdrop-blur">
        <div className="mx-auto flex max-w-6xl flex-col gap-3 px-4 py-3 sm:px-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-sm font-semibold text-[color:var(--accent)]">{t("brand.field")}</p>
              <h1 className="text-xl font-bold leading-tight text-panel-strong sm:text-2xl">{t("page.title")}</h1>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <label className="inline-flex min-h-9 items-center gap-2 rounded-md border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] px-3 text-sm font-semibold text-panel-copy">
                <Languages className="size-4" aria-hidden="true" />
                <span className="sr-only">{t("language.label")}</span>
                <select
                  value={selectedLanguage}
                  onChange={(event) => void handleLanguageChange(event.target.value)}
                  disabled={isChangingLanguage}
                  aria-label={t("language.label")}
                  className="bg-transparent text-sm font-semibold text-panel-strong outline-none"
                >
                  {CHV_LANGUAGE_OPTIONS.map((option) => (
                    <option key={option.code} value={option.code}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
              <div
                className="grid grid-cols-3 gap-1 rounded-md border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] p-1"
                role="group"
                aria-label={t("appearance.label")}
              >
                {APPEARANCE_OPTIONS.map((option) => {
                  const Icon = option.icon;
                  const isActive = appearancePreference === option.value;
                  const label = t(option.labelKey);
                  return (
                    <button
                      key={option.value}
                      type="button"
                      onClick={() => {
                        void handleAppearanceChange(option.value);
                      }}
                      disabled={!canUpdateAppearance || isChangingAppearance}
                      aria-label={label}
                      aria-pressed={isActive}
                      title={label}
                      className={cn(
                        "inline-flex min-h-7 min-w-8 items-center justify-center gap-1.5 rounded px-2 text-xs font-semibold transition",
                        "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[color:var(--accent)]",
                        isActive
                          ? "bg-[color:var(--accent)] text-white shadow-sm"
                          : "text-panel-muted hover:bg-[color-mix(in_srgb,var(--dashboard-table-line)_32%,transparent)] hover:text-panel-strong",
                        (!canUpdateAppearance || isChangingAppearance) && "cursor-not-allowed opacity-60",
                      )}
                    >
                      <Icon className="size-4" aria-hidden="true" />
                      <span className="hidden sm:inline">{label}</span>
                    </button>
                  );
                })}
              </div>
              <StatusBadge status={isOnline ? "online" : "offline"} label={statusLabel(isOnline ? "online" : "offline", t)} />
              <span className="inline-flex min-h-9 items-center gap-2 rounded-md border border-panel-table-wrap bg-[color-mix(in_srgb,var(--dashboard-table-line)_24%,transparent)] px-3 text-sm font-semibold text-panel-copy">
                {isOnline ? <Wifi className="size-4" aria-hidden="true" /> : <WifiOff className="size-4" aria-hidden="true" />}
                {t("status.pendingCount", { count: pendingCount })}
              </span>
              {rejectedCount > 0 ? (
                <span className="inline-flex min-h-9 items-center gap-2 rounded-md border border-[color-mix(in_srgb,var(--danger)_30%,transparent)] bg-[color-mix(in_srgb,var(--danger)_12%,transparent)] px-3 text-sm font-semibold text-[color:var(--danger)]">
                  <XCircle className="size-4" aria-hidden="true" />
                  {t("status.rejectedCount", { count: rejectedCount })}
                </span>
              ) : null}
              {store.bundleMetadata?.fallbackUsed ? (
                <StatusBadge status="pending" label={t("language.fallback")} />
              ) : null}
              {bundleContentUnavailable ? (
                <StatusBadge status="unavailable" label={t("status.unavailable")} />
              ) : null}
            </div>
          </div>

          <nav className="grid grid-cols-5 gap-2" aria-label={t("nav.ariaLabel")}>
            {VIEWS.map((view) => {
              const Icon = view.icon;
              const isActive = activeView === view.id;
              return (
                <button
                  key={view.id}
                  type="button"
                  aria-pressed={isActive}
                  onClick={() => setActiveView(view.id)}
                  className={`flex min-h-12 items-center justify-center gap-2 rounded-lg border px-2 text-sm font-semibold transition ${
                    isActive
                      ? "border-[color:var(--accent)] bg-[color:var(--accent)] text-white"
                      : "border-panel-table-wrap bg-panel text-panel-copy hover:border-[color-mix(in_srgb,var(--accent)_42%,var(--dashboard-table-wrap-border))] hover:text-panel-strong"
                  }`}
                >
                  <Icon className="size-4 shrink-0" aria-hidden="true" />
                  <span className="hidden sm:inline">{t(view.labelKey)}</span>
                </button>
              );
            })}
          </nav>
        </div>
      </header>

      <div className="mx-auto grid max-w-6xl gap-4 px-4 py-4 sm:px-5 lg:grid-cols-[minmax(0,1fr)_340px]">
        <section className="min-w-0">
          {activeView === "tasks" ? (
            <div className="grid gap-4 lg:grid-cols-[320px_minmax(0,1fr)]">
              <section className="rounded-lg border border-panel-border bg-panel p-3 shadow-sm">
                <div className="mb-3 flex items-center justify-between">
                  <h2 className="text-lg font-bold text-panel-strong">{t("task.list")}</h2>
                  <span className="text-sm font-semibold text-panel-subtle">{store.assignedTasks.length}</span>
                </div>
                <div className="grid gap-2">
                  {store.assignedTasks.map((task) => {
                    const status = taskStatus(store, task);
                    const isSelected = selectedTask?.taskPublicId === task.taskPublicId;
                    return (
                      <button
                        key={task.taskPublicId}
                        type="button"
                        onClick={() => setSelectedTaskId(task.taskPublicId)}
                        aria-pressed={isSelected}
                        className={`min-h-24 rounded-lg border p-3 text-left transition ${
                          isSelected
                            ? "border-[color-mix(in_srgb,var(--accent)_60%,var(--dashboard-table-wrap-border))] bg-[color-mix(in_srgb,var(--accent)_12%,transparent)]"
                            : "border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] hover:border-[color-mix(in_srgb,var(--accent)_42%,var(--dashboard-table-wrap-border))]"
                        }`}
                      >
                        <div className="mb-2 flex items-start justify-between gap-2">
                          <span className="font-semibold text-panel-strong">{titleFromTask(task, t)}</span>
                          <StatusBadge status={status} label={statusLabel(status, t)} />
                        </div>
                        <div className="flex items-center gap-2 text-sm text-panel-muted">
                          <MapPin className="size-4" aria-hidden="true" />
                          {t("task.dueAt", { date: formatShortDate(task.dueAt, selectedLanguage) })}
                        </div>
                      </button>
                    );
                  })}
                </div>
              </section>

              <section className="rounded-lg border border-panel-border bg-panel p-4 shadow-sm">
                {selectedTask ? (
                  <>
                    <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <h2 className="text-2xl font-bold leading-tight text-panel-strong">{titleFromTask(selectedTask, t)}</h2>
                        <p className="mt-1 text-sm text-panel-muted">{currentUser.ward_name ?? t("ward.assignedFallback")}</p>
                      </div>
                      <StatusBadge status={taskStatus(store, selectedTask)} label={statusLabel(taskStatus(store, selectedTask), t)} />
                    </div>
                    <dl className="grid gap-3 sm:grid-cols-3">
                      <div className="rounded-lg border border-panel-table-wrap bg-[color-mix(in_srgb,var(--dashboard-table-line)_24%,transparent)] p-3">
                        <dt className="text-xs font-semibold text-panel-subtle">{t("task.priority")}</dt>
                        <dd className="mt-1 text-base font-bold text-panel-strong">{selectedTask.priority}</dd>
                      </div>
                      <div className="rounded-lg border border-panel-table-wrap bg-[color-mix(in_srgb,var(--dashboard-table-line)_24%,transparent)] p-3">
                        <dt className="text-xs font-semibold text-panel-subtle">{t("task.due")}</dt>
                        <dd className="mt-1 text-base font-bold text-panel-strong">{formatShortDate(selectedTask.dueAt, selectedLanguage)}</dd>
                      </div>
                      <div className="rounded-lg border border-panel-table-wrap bg-[color-mix(in_srgb,var(--dashboard-table-line)_24%,transparent)] p-3">
                        <dt className="text-xs font-semibold text-panel-subtle">{t("task.bundle")}</dt>
                        <dd className="mt-1 text-base font-bold text-panel-strong">
                          {bundleFreshness?.isStale ? t("status.stale") : t("status.ready")}
                        </dd>
                      </div>
                    </dl>
                    <div className="mt-5 grid gap-3 sm:grid-cols-2">
                      <Button size="lg" onClick={() => setActiveView("triage")} className="min-h-14">
                        <HeartPulse className="size-5" aria-hidden="true" />
                        {t("task.startTriage")}
                      </Button>
                      <Button size="lg" variant="secondary" onClick={() => setActiveView("guidance")} className="min-h-14">
                        <BookOpen className="size-5" aria-hidden="true" />
                        {t("task.openGuidance")}
                      </Button>
                    </div>
                    {selectedTask.taskType === "preparedness_action" ? (
                      <div className="mt-5 rounded-lg border border-panel-table-wrap bg-[color-mix(in_srgb,var(--dashboard-table-line)_24%,transparent)] p-4">
                        <div className="flex flex-wrap items-center justify-between gap-3">
                          <div>
                            <h3 className="text-lg font-bold text-panel-strong">{t("task.fieldAction")}</h3>
                            <p className="mt-1 text-sm text-panel-muted">{t("task.fieldActionHelp")}</p>
                          </div>
                          <Button
                            size="sm"
                            variant="secondary"
                            onClick={handleAcknowledgeTask}
                            disabled={!selectedTask.allowedUploadTypes.includes("task_ack")}
                          >
                            {t("task.acknowledge")}
                          </Button>
                        </div>

                        {selectedTask.allowedUploadTypes.includes("prevention_visit") ? (
                          <div className="mt-4 grid gap-3">
                            <div className="grid gap-3 sm:grid-cols-2">
                              <label className="block text-sm font-semibold text-panel-copy">
                                {t("task.householdsReached")}
                                <input
                                  type="number"
                                  min={0}
                                  value={preventionVisit.householdsReachedCount}
                                  onChange={(event) =>
                                    updatePreventionVisitField("householdsReachedCount", Number(event.target.value))
                                  }
                                  className="mt-2 h-12 w-full rounded-lg border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] px-3 text-base text-panel-strong outline-none focus:border-[color:var(--accent)] focus:ring-2 focus:ring-[color-mix(in_srgb,var(--accent)_18%,transparent)]"
                                />
                              </label>
                              <label className="block text-sm font-semibold text-panel-copy">
                                {t("task.messagesDelivered")}
                                <input
                                  type="number"
                                  min={0}
                                  value={preventionVisit.messagesDeliveredCount}
                                  onChange={(event) =>
                                    updatePreventionVisitField("messagesDeliveredCount", Number(event.target.value))
                                  }
                                  className="mt-2 h-12 w-full rounded-lg border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] px-3 text-base text-panel-strong outline-none focus:border-[color:var(--accent)] focus:ring-2 focus:ring-[color-mix(in_srgb,var(--accent)_18%,transparent)]"
                                />
                              </label>
                            </div>
                            <div className="grid gap-2 sm:grid-cols-2">
                              <label className="flex min-h-12 items-center gap-3 rounded-lg border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] px-3 text-sm font-semibold text-panel-copy">
                                <input
                                  type="checkbox"
                                  checked={preventionVisit.waterTreatmentDemo}
                                  onChange={(event) => updatePreventionVisitField("waterTreatmentDemo", event.target.checked)}
                                  className="size-4 accent-[var(--accent)]"
                                />
                                {t("task.waterTreatmentDemo")}
                              </label>
                              <label className="flex min-h-12 items-center gap-3 rounded-lg border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] px-3 text-sm font-semibold text-panel-copy">
                                <input
                                  type="checkbox"
                                  checked={preventionVisit.soapOrHandwashingDiscussed}
                                  onChange={(event) =>
                                    updatePreventionVisitField("soapOrHandwashingDiscussed", event.target.checked)
                                  }
                                  className="size-4 accent-[var(--accent)]"
                                />
                                {t("task.soapOrHandwashing")}
                              </label>
                            </div>
                            <Button size="lg" onClick={handleSavePreventionVisit} className="min-h-14">
                              <ClipboardCheck className="size-5" aria-hidden="true" />
                              {t("task.savePreventionVisit")}
                            </Button>
                          </div>
                        ) : null}
                      </div>
                    ) : null}
                  </>
                ) : (
                  <div className="flex min-h-72 items-center justify-center text-center text-panel-muted">
                    {t("task.none")}
                  </div>
                )}
              </section>
            </div>
          ) : null}

          {activeView === "triage" ? (
            <section className="rounded-lg border border-panel-border bg-panel p-4 shadow-sm">
              <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h2 className="text-2xl font-bold text-panel-strong">{t("triage.title")}</h2>
                  <p className="mt-1 text-sm text-panel-muted">{selectedTask ? titleFromTask(selectedTask, t) : t("triage.noTask")}</p>
                </div>
                {selectedTask ? (
                  <StatusBadge status={taskStatus(store, selectedTask)} label={statusLabel(taskStatus(store, selectedTask), t)} />
                ) : null}
              </div>

              <div className="grid gap-3 sm:grid-cols-2">
                {SYMPTOM_OPTIONS.map(({ field, labelKey, icon: Icon }) => {
                  const checked = triage[field];
                  const label = t(labelKey);
                  return (
                    <button
                      key={field}
                      type="button"
                      aria-pressed={checked}
                      onClick={() => updateTriageField(field, !checked)}
                      className={`flex min-h-16 items-center justify-between rounded-lg border p-4 text-left font-semibold transition ${
                        checked
                          ? "border-[color:var(--accent)] bg-[color-mix(in_srgb,var(--accent)_12%,transparent)] text-panel-strong"
                          : "border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] text-panel-copy"
                      }`}
                    >
                      <span className="inline-flex items-center gap-3">
                        <Icon className="size-5" aria-hidden="true" />
                        {label}
                      </span>
                      {checked ? <CheckCircle2 className="size-5 text-[color:var(--accent)]" aria-hidden="true" /> : null}
                    </button>
                  );
                })}
              </div>

              <label className="mt-4 block text-sm font-semibold text-panel-copy" htmlFor="triage-note">
                {t("triage.shortNote")}
              </label>
              <textarea
                id="triage-note"
                value={triage.textInput}
                onChange={(event) => updateTriageField("textInput", event.target.value)}
                rows={3}
                className="mt-2 w-full rounded-lg border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] px-3 py-3 text-base text-panel-strong outline-none transition placeholder:text-panel-subtle focus:border-[color:var(--accent)] focus:ring-2 focus:ring-[color-mix(in_srgb,var(--accent)_18%,transparent)]"
                placeholder={t("triage.optional")}
              />

              <div className={`mt-4 rounded-lg border p-4 ${
                recommendation.tone === "urgent"
                  ? "border-[color-mix(in_srgb,var(--danger)_30%,transparent)] bg-[color-mix(in_srgb,var(--danger)_12%,transparent)]"
                  : recommendation.tone === "warning"
                    ? "border-[color-mix(in_srgb,var(--warning)_30%,transparent)] bg-[color-mix(in_srgb,var(--warning)_12%,transparent)]"
                    : recommendation.tone === "advice"
                      ? "border-[color-mix(in_srgb,var(--success)_28%,transparent)] bg-[color-mix(in_srgb,var(--success)_12%,transparent)]"
                      : "border-panel-table-wrap bg-[color-mix(in_srgb,var(--dashboard-table-line)_24%,transparent)]"
              }`}>
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <p className="font-bold text-panel-strong">{recommendation.title}</p>
                  {recommendation.contentUnavailable ? (
                    <StatusBadge status="unavailable" label={t("status.unavailable")} />
                  ) : recommendation.fallbackUsed ? (
                    <StatusBadge status="pending" label={t("language.fallback")} />
                  ) : null}
                </div>
                <p className="mt-1 text-sm text-panel-copy">{recommendation.body}</p>
                {recommendation.fallbackUsed && !recommendation.contentUnavailable ? (
                  <p className="mt-3 text-sm font-semibold text-[color:var(--warning)]">{t("triage.recommendationFallback")}</p>
                ) : null}
              </div>

              <div className="mt-5 flex flex-col gap-3 sm:flex-row">
                <Button size="lg" onClick={handleSaveTriage} disabled={!selectedTask || !hasSymptoms} className="min-h-14 flex-1">
                  <ClipboardCheck className="size-5" aria-hidden="true" />
                  {t("triage.saveFollowUp")}
                </Button>
                <Button size="lg" variant="secondary" onClick={() => setTriage(EMPTY_TRIAGE)} className="min-h-14 sm:w-44">
                  {t("triage.clear")}
                </Button>
              </div>
            </section>
          ) : null}

          {activeView === "guidance" ? (
            <section className="rounded-lg border border-panel-border bg-panel p-4 shadow-sm">
              <div className="mb-4 flex items-center justify-between gap-3">
                <div>
                  <h2 className="text-2xl font-bold text-panel-strong">{t("guidance.title")}</h2>
                  <p className="mt-1 text-sm text-panel-muted">{currentUser.ward_name ?? t("ward.assignedFallback")}</p>
                </div>
                <BookOpen className="size-6 text-[color:var(--accent)]" aria-hidden="true" />
              </div>
              <div className="grid gap-3">
                {store.wardGuidance.length === 0 ? (
                  <article className="rounded-lg border border-[color-mix(in_srgb,var(--warning)_30%,transparent)] bg-[color-mix(in_srgb,var(--warning)_12%,transparent)] p-4">
                    <h3 className="text-lg font-bold text-panel-strong">{t("guidance.emptyTitle")}</h3>
                    <p className="mt-2 text-base leading-7 text-panel-copy">{t("guidance.emptyBody")}</p>
                  </article>
                ) : (
                  store.wardGuidance.map((item) => (
                    <article key={item.guidancePublicId} className="rounded-lg border border-panel-table-wrap bg-[color-mix(in_srgb,var(--dashboard-table-line)_24%,transparent)] p-4">
                      <div className="flex flex-wrap items-start justify-between gap-2">
                        <h3 className="text-lg font-bold text-panel-strong">{item.title}</h3>
                        {item.fallbackUsed ? <StatusBadge status="pending" label={t("language.fallback")} /> : null}
                      </div>
                      <p className="mt-2 text-base leading-7 text-panel-copy">{item.body}</p>
                      {item.fallbackUsed ? (
                        <p className="mt-3 text-sm font-semibold text-[color:var(--warning)]">{t("guidance.fallbackItem")}</p>
                      ) : null}
                    </article>
                  ))
                )}
              </div>
            </section>
          ) : null}

          {activeView === "sync" ? (
            <section className="rounded-lg border border-panel-border bg-panel p-4 shadow-sm">
              <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h2 className="text-2xl font-bold text-panel-strong">{t("sync.title")}</h2>
                  <p className="mt-1 text-sm text-panel-muted">
                    {t("sync.lastSync", { date: formatShortDate(store.lastSuccessfulSync?.lastSuccessfulSyncAt, selectedLanguage) })}
                  </p>
                </div>
                <Button
                  size="lg"
                  onClick={handleSyncNow}
                  disabled={isSyncing || !isOnline || pendingCount === 0}
                  className="min-h-14"
                >
                  {isSyncing ? <Loader2 className="size-5 animate-spin" aria-hidden="true" /> : <Send className="size-5" aria-hidden="true" />}
                  {t("sync.now")}
                </Button>
              </div>

              {syncMessage ? (
                <div className="mb-4 rounded-lg border border-panel-table-wrap bg-[color-mix(in_srgb,var(--dashboard-table-line)_24%,transparent)] p-3 text-sm font-semibold text-panel-copy">
                  {syncMessage}
                </div>
              ) : null}

              <div className="grid gap-3">
                {store.pendingSyncItems.map((item) => (
                  <div key={item.localId} className="flex min-h-16 items-center justify-between gap-3 rounded-lg border border-[color-mix(in_srgb,var(--warning)_30%,transparent)] bg-[color-mix(in_srgb,var(--warning)_12%,transparent)] p-3">
                    <div>
                      <p className="font-bold text-panel-strong">{uploadTypeLabel(item.uploadType, t)}</p>
                      <p className="text-sm text-panel-muted">{t("sync.queuedAt", { date: formatShortDate(item.createdAt, selectedLanguage) })}</p>
                    </div>
                    <StatusBadge status="pending" label={statusLabel("pending", t)} />
                  </div>
                ))}
                {store.failedSyncItems.map((item) => (
                  <div key={item.localId} className="rounded-lg border border-[color-mix(in_srgb,var(--danger)_30%,transparent)] bg-[color-mix(in_srgb,var(--danger)_12%,transparent)] p-3">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="font-bold text-panel-strong">{statusLabel("rejected", t)}</p>
                        <p className="mt-1 text-sm text-panel-copy">{item.failureReason}</p>
                      </div>
                      <StatusBadge status="rejected" label={statusLabel("rejected", t)} />
                    </div>
                  </div>
                ))}
                {pendingCount === 0 && rejectedCount === 0 ? (
                  <div className="rounded-lg border border-[color-mix(in_srgb,var(--success)_28%,transparent)] bg-[color-mix(in_srgb,var(--success)_12%,transparent)] p-4 text-sm font-semibold text-[color:var(--success)]">
                    {t("sync.allSent")}
                  </div>
                ) : null}
              </div>

              <div className="mt-5 border-t border-panel-table-wrap pt-4">
                <div className="mb-3 flex items-center justify-between">
                  <h3 className="text-lg font-bold text-panel-strong">{t("sync.conflictReview")}</h3>
                  <StatusBadge
                    status={conflictCount > 0 ? "pending" : "clear"}
                    label={conflictCount > 0 ? t("status.openCount", { count: conflictCount }) : statusLabel("clear", t)}
                  />
                </div>
                <div className="grid gap-3">
                  {store.conflictItems.filter((item) => item.resolutionStatus === "UNRESOLVED").map((item) => (
                    <div key={item.localId} className="rounded-lg border border-[color-mix(in_srgb,var(--warning)_30%,transparent)] bg-[color-mix(in_srgb,var(--warning)_12%,transparent)] p-3">
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <div>
                          <p className="font-bold text-panel-strong">{conflictLabel(item.conflictState, t)}</p>
                          <p className="text-sm text-panel-muted">{uploadTypeLabel(item.uploadType, t)}</p>
                        </div>
                        <Button size="sm" variant="secondary" onClick={() => dismissConflict(item.localId)}>
                          {t("sync.dismiss")}
                        </Button>
                      </div>
                    </div>
                  ))}
                  {conflictCount === 0 ? (
                    <div className="rounded-lg border border-panel-table-wrap bg-[color-mix(in_srgb,var(--dashboard-table-line)_24%,transparent)] p-3 text-sm font-semibold text-panel-muted">
                      {t("sync.noConflicts")}
                    </div>
                  ) : null}
                </div>
              </div>
            </section>
          ) : null}

          {activeView === "profile" ? (
            <section className="rounded-lg border border-panel-border bg-panel p-4 shadow-sm">
              <div className="mb-4 flex items-center gap-3">
                <span className="inline-flex size-12 items-center justify-center rounded-lg bg-[color-mix(in_srgb,var(--accent)_14%,transparent)] text-[color:var(--accent)]">
                  <UserRound className="size-6" aria-hidden="true" />
                </span>
                <div>
                  <h2 className="text-2xl font-bold text-panel-strong">{currentUser.full_name || currentUser.username}</h2>
                  <p className="text-sm font-semibold text-panel-muted">{currentUser.role}</p>
                </div>
              </div>
              <dl className="grid gap-3 sm:grid-cols-2">
                <div className="rounded-lg border border-panel-table-wrap bg-[color-mix(in_srgb,var(--dashboard-table-line)_24%,transparent)] p-3">
                  <dt className="text-xs font-semibold text-panel-subtle">{t("profile.ward")}</dt>
                  <dd className="mt-1 text-base font-bold text-panel-strong">{currentUser.ward_name ?? t("ward.unassigned")}</dd>
                </div>
                <div className="rounded-lg border border-panel-table-wrap bg-[color-mix(in_srgb,var(--dashboard-table-line)_24%,transparent)] p-3">
                  <dt className="text-xs font-semibold text-panel-subtle">{t("profile.device")}</dt>
                  <dd className="mt-1 break-all text-base font-bold text-panel-strong">{deviceId || t("profile.localBrowser")}</dd>
                </div>
                <div className="rounded-lg border border-panel-table-wrap bg-[color-mix(in_srgb,var(--dashboard-table-line)_24%,transparent)] p-3">
                  <dt className="text-xs font-semibold text-panel-subtle">{t("profile.bundle")}</dt>
                  <dd className="mt-1 text-base font-bold text-panel-strong">
                    {store.bundleMetadata?.downloadBundleVersion ?? t("profile.localFallback")}
                  </dd>
                </div>
                <div className="rounded-lg border border-panel-table-wrap bg-[color-mix(in_srgb,var(--dashboard-table-line)_24%,transparent)] p-3">
                  <dt className="text-xs font-semibold text-panel-subtle">{t("profile.expires")}</dt>
                  <dd className="mt-1 text-base font-bold text-panel-strong">{formatShortDate(store.bundleMetadata?.expiresAt, selectedLanguage)}</dd>
                </div>
                <div className="rounded-lg border border-panel-table-wrap bg-[color-mix(in_srgb,var(--dashboard-table-line)_24%,transparent)] p-3">
                  <dt className="text-xs font-semibold text-panel-subtle">{t("language.bundle")}</dt>
                  <dd className="mt-1 text-base font-bold text-panel-strong">
                    {store.bundleMetadata?.resolvedLanguage.toUpperCase() ?? selectedLanguage.toUpperCase()}
                    {store.bundleMetadata?.fallbackUsed ? ` · ${t("language.fallback")}` : ""}
                    {bundleContentUnavailable ? ` · ${t("status.unavailable")}` : ""}
                  </dd>
                </div>
              </dl>
            </section>
          ) : null}
        </section>

        <aside className="grid content-start gap-4">
          <section className="rounded-lg border border-panel-border bg-panel p-4 shadow-sm">
            <div className="mb-3 flex items-center justify-between gap-3">
              <h2 className="text-lg font-bold text-panel-strong">{t("offline.title")}</h2>
              {isOnline ? <Cloud className="size-5 text-[color:var(--accent)]" aria-hidden="true" /> : <CloudOff className="size-5 text-[color:var(--warning)]" aria-hidden="true" />}
            </div>
            <div className="grid gap-2 text-sm">
              <div className="flex items-center justify-between gap-3 rounded-lg border border-panel-table-wrap bg-[color-mix(in_srgb,var(--dashboard-table-line)_24%,transparent)] p-3">
                <span className="font-semibold text-panel-muted">{t("offline.connection")}</span>
                <span className="font-bold text-panel-strong">{statusLabel(isOnline ? "online" : "offline", t)}</span>
              </div>
              <div className="flex items-center justify-between gap-3 rounded-lg border border-panel-table-wrap bg-[color-mix(in_srgb,var(--dashboard-table-line)_24%,transparent)] p-3">
                <span className="font-semibold text-panel-muted">{t("offline.work")}</span>
                <span className="font-bold text-panel-strong">{t("status.pendingCount", { count: pendingCount })}</span>
              </div>
              <div className="flex items-center justify-between gap-3 rounded-lg border border-panel-table-wrap bg-[color-mix(in_srgb,var(--dashboard-table-line)_24%,transparent)] p-3">
                <span className="font-semibold text-panel-muted">{t("offline.bundle")}</span>
                <span className="font-bold text-panel-strong">{bundleFreshness?.isStale ? statusLabel("stale", t) : statusLabel("ready", t)}</span>
              </div>
            </div>
          </section>

          <section className="rounded-lg border border-panel-border bg-panel p-4 shadow-sm">
            <div className="mb-3 flex items-center gap-2">
              <FileWarning className="size-5 text-[color:var(--warning)]" aria-hidden="true" />
              <h2 className="text-lg font-bold text-panel-strong">{t("nextAction.title")}</h2>
            </div>
            <p className="text-sm font-semibold leading-6 text-panel-copy">
              {pendingCount > 0
                ? isOnline
                  ? t("nextAction.syncPending")
                  : t("nextAction.keepSaved")
                : selectedTask
                  ? t("nextAction.openTriage")
                  : t("nextAction.waitAssignment")}
            </p>
            <Button
              size="lg"
              variant={pendingCount > 0 ? "primary" : "secondary"}
              onClick={() => (pendingCount > 0 ? setActiveView("sync") : setActiveView("triage"))}
              className="mt-4 min-h-14 w-full"
            >
              {pendingCount > 0 ? <RefreshCw className="size-5" aria-hidden="true" /> : <HeartPulse className="size-5" aria-hidden="true" />}
              {pendingCount > 0 ? t("nextAction.openSync") : t("nextAction.openTriage")}
            </Button>
          </section>
        </aside>
      </div>
    </main>
  );
}

export default function ChvOfflinePage() {
  const router = useRouter();
  const { currentUser, isAuthenticated, isHydrating } = useAuth();

  useEffect(() => {
    if (isHydrating) {
      return;
    }

    if (!isAuthenticated || !currentUser) {
      router.replace("/login");
      return;
    }

    if (!canUseChvOffline(currentUser.role)) {
      router.replace("/unauthorized");
    }
  }, [currentUser, isAuthenticated, isHydrating, router]);

  if (isHydrating) {
    return (
      <PublicScreen>
        <PublicCard>
          <div className="inline-flex items-center gap-3 text-sm font-semibold text-panel-copy">
            <Loader2 className="size-5 animate-spin" aria-hidden="true" />
            {chvTranslate("en", "app.restoringSession")}
          </div>
        </PublicCard>
      </PublicScreen>
    );
  }

  if (!isAuthenticated || !currentUser || !canUseChvOffline(currentUser.role)) {
    return null;
  }

  return <ChvOfflineWorkspace currentUser={currentUser} />;
}
