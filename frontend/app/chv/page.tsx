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
  Loader2,
  MapPin,
  RefreshCw,
  Send,
  ShieldCheck,
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
import type { CurrentUser } from "@/lib/auth";
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
  markChvAssignedTaskStatus,
  markChvPendingSyncItemAttempted,
  markChvSyncItemSent,
  movePendingSyncItemToFailed,
  queueChvPendingSyncItem,
  readChvOfflineStore,
  recordChvSyncConflict,
  upsertPreventionVisitDraft,
  upsertSymptomTriageDraft,
  writeChvOfflineStore,
  type ChvOfflineAssignedTask,
  type ChvOfflineDownloadBundleInput,
  type ChvOfflineLocalStore,
  type ChvOfflineUploadType,
} from "@/lib/chv-offline-store";
import { canUseChvOffline } from "@/lib/roles";

type ChvView = "tasks" | "triage" | "guidance" | "sync" | "profile";

type TriageState = {
  diarrhea: boolean;
  vomiting: boolean;
  dehydration: boolean;
  fever: boolean;
  textInput: string;
};

type PreventionVisitState = {
  householdsReachedCount: number;
  messagesDeliveredCount: number;
  waterTreatmentDemo: boolean;
  soapOrHandwashingDiscussed: boolean;
};

type SymptomOption = {
  field: Exclude<keyof TriageState, "textInput">;
  label: string;
  icon: LucideIcon;
};

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

const VIEWS: Array<{ id: ChvView; label: string; icon: LucideIcon }> = [
  { id: "tasks", label: "Tasks", icon: ClipboardList },
  { id: "triage", label: "Triage", icon: HeartPulse },
  { id: "guidance", label: "Guidance", icon: BookOpen },
  { id: "sync", label: "Sync", icon: Cloud },
  { id: "profile", label: "Profile", icon: UserRound },
];

const SYMPTOM_OPTIONS: SymptomOption[] = [
  { field: "diarrhea", label: "Diarrhea", icon: HeartPulse },
  { field: "vomiting", label: "Vomiting", icon: AlertTriangle },
  { field: "dehydration", label: "Dehydration", icon: ShieldCheck },
  { field: "fever", label: "Fever", icon: Thermometer },
];

function addHours(now: Date, hours: number) {
  return new Date(now.getTime() + hours * 60 * 60 * 1000).toISOString();
}

function buildScopeKey(user: CurrentUser) {
  const wardPart = user.ward ? `ward-${user.ward}` : "ward-unassigned";
  return `${wardPart}.user-${user.id}`;
}

function buildFallbackBundle(user: CurrentUser, now: Date): ChvOfflineDownloadBundleInput {
  const wardId = user.ward ?? 0;
  const wardName = user.ward_name ?? "Assigned ward";
  const wardPublicId = `local-ward-${wardId || user.id}`;

  return {
    version: `chv-bundle-local-phase3-${wardId || user.id}`,
    generated_at: now.toISOString(),
    expires_at: addHours(now, 24),
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
      items: [
        {
          guidance_public_id: "cholera-prevention-safe-water-v1",
          template_key: "cholera.prevention.safe_water",
          language: "en",
          version: 1,
          audience_type: "CHV",
          title: "Safe water",
          body: "Treat drinking water, store it covered, and use a clean cup or ladle.",
        },
        {
          guidance_public_id: "cholera-prevention-handwashing-v1",
          template_key: "cholera.prevention.handwashing",
          language: "en",
          version: 1,
          audience_type: "CHV",
          title: "Handwashing",
          body: "Wash hands with soap after using the toilet and before preparing food.",
        },
        {
          guidance_public_id: "cholera-prevention-referral-v1",
          template_key: "cholera.prevention.referral",
          language: "en",
          version: 1,
          audience_type: "CHV",
          title: "Danger signs",
          body: `Refer dehydration signs to the nearest active facility serving ${wardName}.`,
        },
      ],
    },
    decision_support_rule_bundle: {
      version: "cholera-triage-rules-v1",
    },
  };
}

function formatShortDate(value: string | null | undefined) {
  if (!value) {
    return "Not set";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "Not set";
  }

  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function titleFromTask(task: ChvOfflineAssignedTask) {
  if (task.actionType === "CHV_FOLLOW_UP") {
    return "Household follow-up";
  }
  if (task.taskType === "chv_coverage_assignment") {
    return "Coverage follow-up";
  }
  return "Ward follow-up";
}

function uploadTypeLabel(uploadType: ChvOfflineUploadType) {
  switch (uploadType) {
    case "prevention_visit":
      return "Prevention visit";
    case "task_ack":
      return "Task acknowledgement";
    case "alert_ack":
      return "Alert acknowledgement";
    case "suspected_case_signal":
      return "Suspected-case signal";
    case "symptom_triage":
    default:
      return "Symptom triage";
  }
}

function taskStatus(store: ChvOfflineLocalStore, task: ChvOfflineAssignedTask) {
  const hasFailed = store.failedSyncItems.some((item) => item.payload.task_public_id === task.taskPublicId);
  if (hasFailed) {
    return "Rejected";
  }

  const hasPending = store.pendingSyncItems.some((item) => item.payload.task_public_id === task.taskPublicId);
  if (hasPending || task.status === "PENDING_SYNC") {
    return "Pending";
  }

  if (task.status === "SENT") {
    return "Sent";
  }

  return "Assigned";
}

function statusClasses(status: string) {
  if (status === "Online" || status === "Clear") {
    return "border-emerald-200 bg-emerald-50 text-emerald-800";
  }
  if (status === "Offline" || status.includes("open")) {
    return "border-amber-200 bg-amber-50 text-amber-800";
  }
  if (status === "Sent") {
    return "border-emerald-200 bg-emerald-50 text-emerald-800";
  }
  if (status === "Pending") {
    return "border-amber-200 bg-amber-50 text-amber-800";
  }
  if (status === "Rejected") {
    return "border-rose-200 bg-rose-50 text-rose-800";
  }
  return "border-slate-200 bg-slate-50 text-slate-700";
}

function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`inline-flex min-h-7 items-center rounded-md border px-2.5 text-xs font-semibold ${statusClasses(status)}`}>
      {status}
    </span>
  );
}

function recommendationFor(triage: TriageState) {
  if (triage.dehydration && (triage.diarrhea || triage.vomiting)) {
    return {
      tone: "urgent",
      title: "Refer now",
      body: "Dehydration signs need facility review.",
    };
  }
  if (triage.diarrhea && (triage.vomiting || triage.fever)) {
    return {
      tone: "warning",
      title: "Facility check",
      body: "Symptoms match the escalation rule.",
    };
  }
  if (triage.diarrhea) {
    return {
      tone: "advice",
      title: "ORS and prevention",
      body: "Give ORS advice and reinforce safe water.",
    };
  }
  return {
    tone: "neutral",
    title: "Record symptoms",
    body: "Select what is present before saving.",
  };
}

function normalizeError(error: unknown) {
  if (error instanceof Error) {
    return error.message;
  }
  return "Unable to sync offline work.";
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

  const persistStore = useCallback((nextStore: ChvOfflineLocalStore) => {
    writeChvOfflineStore(nextStore);
    setStore(nextStore);
  }, []);

  useEffect(() => {
    let isCancelled = false;
    const nextDeviceId = getOrCreateChvOfflineDeviceId();
    setDeviceId(nextDeviceId);
    setDeviceRegistrationId(getStoredChvOfflineDeviceRegistrationId());

    const now = new Date();
    const scopeKey = buildScopeKey(currentUser);
    const stored = applyChvOfflineRetentionRules(readChvOfflineStore(scopeKey, undefined, now), now);
    const initialized =
      stored.bundleMetadata || typeof currentUser.ward !== "number"
        ? stored
        : cacheChvOfflineDownloadBundle(stored, buildFallbackBundle(currentUser, now), undefined, now);

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
          fetchChvOfflineContractViaBff(),
          postChvDeviceRegistrationViaBff({
            device_id: nextDeviceId,
            contract_version: "chv-offline-v1",
            platform: "WEB",
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
          setSyncMessage("Using the local fallback bundle until the live assignment bundle is available.");
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
  const recommendation = recommendationFor(triage);

  function updateTriageField(field: keyof TriageState, value: boolean | string) {
    setTriage((current) => ({ ...current, [field]: value }));
  }

  function handleSaveTriage() {
    if (!store || !selectedTask || !hasSymptoms) {
      setSyncMessage("Select at least one symptom before saving.");
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
    setSyncMessage("Follow-up saved on this device.");
  }

  function handleAcknowledgeTask() {
    if (!store || !selectedTask) {
      return;
    }
    if (selectedTask.taskType !== "preparedness_action" || !selectedTask.allowedUploadTypes.includes("task_ack")) {
      setSyncMessage("This task cannot be acknowledged offline.");
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
    setSyncMessage("Task acknowledgement saved on this device.");
  }

  function updatePreventionVisitField(field: keyof PreventionVisitState, value: boolean | number) {
    setPreventionVisit((current) => ({ ...current, [field]: value }));
  }

  function handleSavePreventionVisit() {
    if (!store || !selectedTask) {
      return;
    }
    if (selectedTask.taskType !== "preparedness_action" || !selectedTask.allowedUploadTypes.includes("prevention_visit")) {
      setSyncMessage("This task cannot record a prevention visit offline.");
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
    setSyncMessage("Prevention visit saved on this device.");
  }

  async function handleSyncNow() {
    if (!store) {
      return;
    }
    if (!isOnline) {
      setSyncMessage("Offline. Pending work will stay on this device.");
      return;
    }

    const syncableItems = store.pendingSyncItems.filter((item) => isChvOfflineUploadSyncable(item.uploadType));
    if (syncableItems.length === 0) {
      setSyncMessage("No pending work to sync.");
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
          const message = normalizeError(error);
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
        const syncParts = [`${sentCount} sent`];
        if (rejectedCountInRun > 0) {
          syncParts.push(`${rejectedCountInRun} rejected`);
        }
        syncParts.push(`${retryLaterCount} waiting to retry`);
        setSyncMessage(`${syncParts.join(", ")}. ${lastFailureMessage}`);
      } else {
        setSyncMessage(
          rejectedCountInRun
            ? `${sentCount} sent, ${rejectedCountInRun} rejected. ${lastFailureMessage}`
            : "Sent.",
        );
      }
    } catch (error) {
      persistStore(nextStore);
      setSyncMessage(normalizeError(error));
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

  if (!store) {
    return (
      <PublicScreen className="min-h-screen bg-[#f6f8fb] text-slate-950">
        <div className="flex min-h-screen items-center justify-center">
          <div className="inline-flex items-center gap-3 text-sm font-semibold text-slate-700">
            <Loader2 className="size-5 animate-spin" aria-hidden="true" />
            Loading CHV workspace
          </div>
        </div>
      </PublicScreen>
    );
  }

  return (
    <main className="min-h-screen bg-[#f6f8fb] text-slate-950">
      <header className="sticky top-0 z-20 border-b border-slate-200 bg-white/95 backdrop-blur">
        <div className="mx-auto flex max-w-6xl flex-col gap-3 px-4 py-3 sm:px-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-sm font-semibold text-teal-800">CCHIS Field</p>
              <h1 className="text-xl font-bold leading-tight text-slate-950 sm:text-2xl">CHV follow-up</h1>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <StatusBadge status={isOnline ? "Online" : "Offline"} />
              <span className="inline-flex min-h-9 items-center gap-2 rounded-md border border-slate-200 bg-slate-50 px-3 text-sm font-semibold text-slate-700">
                {isOnline ? <Wifi className="size-4" aria-hidden="true" /> : <WifiOff className="size-4" aria-hidden="true" />}
                {pendingCount} pending
              </span>
              {rejectedCount > 0 ? (
                <span className="inline-flex min-h-9 items-center gap-2 rounded-md border border-rose-200 bg-rose-50 px-3 text-sm font-semibold text-rose-800">
                  <XCircle className="size-4" aria-hidden="true" />
                  {rejectedCount} rejected
                </span>
              ) : null}
            </div>
          </div>

          <nav className="grid grid-cols-5 gap-2" aria-label="CHV offline views">
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
                      ? "border-teal-600 bg-teal-700 text-white"
                      : "border-slate-200 bg-white text-slate-700 hover:border-teal-300"
                  }`}
                >
                  <Icon className="size-4 shrink-0" aria-hidden="true" />
                  <span className="hidden sm:inline">{view.label}</span>
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
              <section className="rounded-lg border border-slate-200 bg-white p-3 shadow-sm">
                <div className="mb-3 flex items-center justify-between">
                  <h2 className="text-lg font-bold text-slate-950">Task list</h2>
                  <span className="text-sm font-semibold text-slate-500">{store.assignedTasks.length}</span>
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
                          isSelected ? "border-teal-500 bg-teal-50" : "border-slate-200 bg-white hover:border-teal-300"
                        }`}
                      >
                        <div className="mb-2 flex items-start justify-between gap-2">
                          <span className="font-semibold text-slate-950">{titleFromTask(task)}</span>
                          <StatusBadge status={status} />
                        </div>
                        <div className="flex items-center gap-2 text-sm text-slate-600">
                          <MapPin className="size-4" aria-hidden="true" />
                          Due {formatShortDate(task.dueAt)}
                        </div>
                      </button>
                    );
                  })}
                </div>
              </section>

              <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
                {selectedTask ? (
                  <>
                    <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <h2 className="text-2xl font-bold leading-tight text-slate-950">{titleFromTask(selectedTask)}</h2>
                        <p className="mt-1 text-sm text-slate-600">{currentUser.ward_name ?? "Assigned ward"}</p>
                      </div>
                      <StatusBadge status={taskStatus(store, selectedTask)} />
                    </div>
                    <dl className="grid gap-3 sm:grid-cols-3">
                      <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
                        <dt className="text-xs font-semibold text-slate-500">Priority</dt>
                        <dd className="mt-1 text-base font-bold text-slate-950">{selectedTask.priority}</dd>
                      </div>
                      <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
                        <dt className="text-xs font-semibold text-slate-500">Due</dt>
                        <dd className="mt-1 text-base font-bold text-slate-950">{formatShortDate(selectedTask.dueAt)}</dd>
                      </div>
                      <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
                        <dt className="text-xs font-semibold text-slate-500">Bundle</dt>
                        <dd className="mt-1 text-base font-bold text-slate-950">
                          {bundleFreshness?.isStale ? "Stale" : "Ready"}
                        </dd>
                      </div>
                    </dl>
                    <div className="mt-5 grid gap-3 sm:grid-cols-2">
                      <Button size="lg" onClick={() => setActiveView("triage")} className="min-h-14">
                        <HeartPulse className="size-5" aria-hidden="true" />
                        Start triage
                      </Button>
                      <Button size="lg" variant="secondary" onClick={() => setActiveView("guidance")} className="min-h-14">
                        <BookOpen className="size-5" aria-hidden="true" />
                        Open guidance
                      </Button>
                    </div>
                    {selectedTask.taskType === "preparedness_action" ? (
                      <div className="mt-5 rounded-lg border border-slate-200 bg-slate-50 p-4">
                        <div className="flex flex-wrap items-center justify-between gap-3">
                          <div>
                            <h3 className="text-lg font-bold text-slate-950">Field action</h3>
                            <p className="mt-1 text-sm text-slate-600">Save task progress for the next sync.</p>
                          </div>
                          <Button
                            size="sm"
                            variant="secondary"
                            onClick={handleAcknowledgeTask}
                            disabled={!selectedTask.allowedUploadTypes.includes("task_ack")}
                          >
                            Acknowledge
                          </Button>
                        </div>

                        {selectedTask.allowedUploadTypes.includes("prevention_visit") ? (
                          <div className="mt-4 grid gap-3">
                            <div className="grid gap-3 sm:grid-cols-2">
                              <label className="block text-sm font-semibold text-slate-700">
                                Households reached
                                <input
                                  type="number"
                                  min={0}
                                  value={preventionVisit.householdsReachedCount}
                                  onChange={(event) =>
                                    updatePreventionVisitField("householdsReachedCount", Number(event.target.value))
                                  }
                                  className="mt-2 h-12 w-full rounded-lg border border-slate-200 bg-white px-3 text-base text-slate-950 outline-none focus:border-teal-500 focus:ring-2 focus:ring-teal-100"
                                />
                              </label>
                              <label className="block text-sm font-semibold text-slate-700">
                                Messages delivered
                                <input
                                  type="number"
                                  min={0}
                                  value={preventionVisit.messagesDeliveredCount}
                                  onChange={(event) =>
                                    updatePreventionVisitField("messagesDeliveredCount", Number(event.target.value))
                                  }
                                  className="mt-2 h-12 w-full rounded-lg border border-slate-200 bg-white px-3 text-base text-slate-950 outline-none focus:border-teal-500 focus:ring-2 focus:ring-teal-100"
                                />
                              </label>
                            </div>
                            <div className="grid gap-2 sm:grid-cols-2">
                              <label className="flex min-h-12 items-center gap-3 rounded-lg border border-slate-200 bg-white px-3 text-sm font-semibold text-slate-700">
                                <input
                                  type="checkbox"
                                  checked={preventionVisit.waterTreatmentDemo}
                                  onChange={(event) => updatePreventionVisitField("waterTreatmentDemo", event.target.checked)}
                                  className="size-4 accent-teal-700"
                                />
                                Water treatment demo
                              </label>
                              <label className="flex min-h-12 items-center gap-3 rounded-lg border border-slate-200 bg-white px-3 text-sm font-semibold text-slate-700">
                                <input
                                  type="checkbox"
                                  checked={preventionVisit.soapOrHandwashingDiscussed}
                                  onChange={(event) =>
                                    updatePreventionVisitField("soapOrHandwashingDiscussed", event.target.checked)
                                  }
                                  className="size-4 accent-teal-700"
                                />
                                Soap or handwashing
                              </label>
                            </div>
                            <Button size="lg" onClick={handleSavePreventionVisit} className="min-h-14">
                              <ClipboardCheck className="size-5" aria-hidden="true" />
                              Save prevention visit
                            </Button>
                          </div>
                        ) : null}
                      </div>
                    ) : null}
                  </>
                ) : (
                  <div className="flex min-h-72 items-center justify-center text-center text-slate-600">
                    No assigned tasks.
                  </div>
                )}
              </section>
            </div>
          ) : null}

          {activeView === "triage" ? (
            <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
              <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h2 className="text-2xl font-bold text-slate-950">Symptom triage</h2>
                  <p className="mt-1 text-sm text-slate-600">{selectedTask ? titleFromTask(selectedTask) : "No task selected"}</p>
                </div>
                {selectedTask ? <StatusBadge status={taskStatus(store, selectedTask)} /> : null}
              </div>

              <div className="grid gap-3 sm:grid-cols-2">
                {SYMPTOM_OPTIONS.map(({ field, label, icon: Icon }) => {
                  const checked = triage[field];
                  return (
                    <button
                      key={field}
                      type="button"
                      aria-pressed={checked}
                      onClick={() => updateTriageField(field, !checked)}
                      className={`flex min-h-16 items-center justify-between rounded-lg border p-4 text-left font-semibold transition ${
                        checked ? "border-teal-600 bg-teal-50 text-teal-950" : "border-slate-200 bg-white text-slate-800"
                      }`}
                    >
                      <span className="inline-flex items-center gap-3">
                        <Icon className="size-5" aria-hidden="true" />
                        {label}
                      </span>
                      {checked ? <CheckCircle2 className="size-5 text-teal-700" aria-hidden="true" /> : null}
                    </button>
                  );
                })}
              </div>

              <label className="mt-4 block text-sm font-semibold text-slate-700" htmlFor="triage-note">
                Short note
              </label>
              <textarea
                id="triage-note"
                value={triage.textInput}
                onChange={(event) => updateTriageField("textInput", event.target.value)}
                rows={3}
                className="mt-2 w-full rounded-lg border border-slate-200 bg-white px-3 py-3 text-base text-slate-950 outline-none transition focus:border-teal-500 focus:ring-2 focus:ring-teal-100"
                placeholder="Optional"
              />

              <div className={`mt-4 rounded-lg border p-4 ${
                recommendation.tone === "urgent"
                  ? "border-rose-200 bg-rose-50"
                  : recommendation.tone === "warning"
                    ? "border-amber-200 bg-amber-50"
                    : recommendation.tone === "advice"
                      ? "border-emerald-200 bg-emerald-50"
                      : "border-slate-200 bg-slate-50"
              }`}>
                <p className="font-bold text-slate-950">{recommendation.title}</p>
                <p className="mt-1 text-sm text-slate-700">{recommendation.body}</p>
              </div>

              <div className="mt-5 flex flex-col gap-3 sm:flex-row">
                <Button size="lg" onClick={handleSaveTriage} disabled={!selectedTask || !hasSymptoms} className="min-h-14 flex-1">
                  <ClipboardCheck className="size-5" aria-hidden="true" />
                  Save follow-up
                </Button>
                <Button size="lg" variant="secondary" onClick={() => setTriage(EMPTY_TRIAGE)} className="min-h-14 sm:w-44">
                  Clear
                </Button>
              </div>
            </section>
          ) : null}

          {activeView === "guidance" ? (
            <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
              <div className="mb-4 flex items-center justify-between gap-3">
                <div>
                  <h2 className="text-2xl font-bold text-slate-950">Prevention guidance</h2>
                  <p className="mt-1 text-sm text-slate-600">{currentUser.ward_name ?? "Assigned ward"}</p>
                </div>
                <BookOpen className="size-6 text-teal-700" aria-hidden="true" />
              </div>
              <div className="grid gap-3">
                {store.wardGuidance.map((item) => (
                  <article key={item.guidancePublicId} className="rounded-lg border border-slate-200 bg-slate-50 p-4">
                    <h3 className="text-lg font-bold text-slate-950">{item.title}</h3>
                    <p className="mt-2 text-base leading-7 text-slate-700">{item.body}</p>
                  </article>
                ))}
              </div>
            </section>
          ) : null}

          {activeView === "sync" ? (
            <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
              <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h2 className="text-2xl font-bold text-slate-950">Pending sync queue</h2>
                  <p className="mt-1 text-sm text-slate-600">
                    Last sync {formatShortDate(store.lastSuccessfulSync?.lastSuccessfulSyncAt)}
                  </p>
                </div>
                <Button
                  size="lg"
                  onClick={handleSyncNow}
                  disabled={isSyncing || !isOnline || pendingCount === 0}
                  className="min-h-14"
                >
                  {isSyncing ? <Loader2 className="size-5 animate-spin" aria-hidden="true" /> : <Send className="size-5" aria-hidden="true" />}
                  Sync now
                </Button>
              </div>

              {syncMessage ? (
                <div className="mb-4 rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm font-semibold text-slate-700">
                  {syncMessage}
                </div>
              ) : null}

              <div className="grid gap-3">
                {store.pendingSyncItems.map((item) => (
                  <div key={item.localId} className="flex min-h-16 items-center justify-between gap-3 rounded-lg border border-amber-200 bg-amber-50 p-3">
                    <div>
                      <p className="font-bold text-slate-950">{uploadTypeLabel(item.uploadType)}</p>
                      <p className="text-sm text-slate-600">Queued {formatShortDate(item.createdAt)}</p>
                    </div>
                    <StatusBadge status="Pending" />
                  </div>
                ))}
                {store.failedSyncItems.map((item) => (
                  <div key={item.localId} className="rounded-lg border border-rose-200 bg-rose-50 p-3">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="font-bold text-slate-950">Rejected</p>
                        <p className="mt-1 text-sm text-slate-700">{item.failureReason}</p>
                      </div>
                      <StatusBadge status="Rejected" />
                    </div>
                  </div>
                ))}
                {pendingCount === 0 && rejectedCount === 0 ? (
                  <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-4 text-sm font-semibold text-emerald-800">
                    All saved work is sent.
                  </div>
                ) : null}
              </div>

              <div className="mt-5 border-t border-slate-200 pt-4">
                <div className="mb-3 flex items-center justify-between">
                  <h3 className="text-lg font-bold text-slate-950">Sync conflict review</h3>
                  <StatusBadge status={conflictCount > 0 ? `${conflictCount} open` : "Clear"} />
                </div>
                <div className="grid gap-3">
                  {store.conflictItems.filter((item) => item.resolutionStatus === "UNRESOLVED").map((item) => (
                    <div key={item.localId} className="rounded-lg border border-amber-200 bg-amber-50 p-3">
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <div>
                          <p className="font-bold text-slate-950">{item.conflictState.replaceAll("_", " ")}</p>
                          <p className="text-sm text-slate-600">{item.uploadType}</p>
                        </div>
                        <Button size="sm" variant="secondary" onClick={() => dismissConflict(item.localId)}>
                          Dismiss
                        </Button>
                      </div>
                    </div>
                  ))}
                  {conflictCount === 0 ? (
                    <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm font-semibold text-slate-600">
                      No conflicts.
                    </div>
                  ) : null}
                </div>
              </div>
            </section>
          ) : null}

          {activeView === "profile" ? (
            <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
              <div className="mb-4 flex items-center gap-3">
                <span className="inline-flex size-12 items-center justify-center rounded-lg bg-teal-50 text-teal-700">
                  <UserRound className="size-6" aria-hidden="true" />
                </span>
                <div>
                  <h2 className="text-2xl font-bold text-slate-950">{currentUser.full_name || currentUser.username}</h2>
                  <p className="text-sm font-semibold text-slate-600">{currentUser.role}</p>
                </div>
              </div>
              <dl className="grid gap-3 sm:grid-cols-2">
                <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
                  <dt className="text-xs font-semibold text-slate-500">Ward</dt>
                  <dd className="mt-1 text-base font-bold text-slate-950">{currentUser.ward_name ?? "Unassigned"}</dd>
                </div>
                <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
                  <dt className="text-xs font-semibold text-slate-500">Device</dt>
                  <dd className="mt-1 break-all text-base font-bold text-slate-950">{deviceId || "Local browser"}</dd>
                </div>
                <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
                  <dt className="text-xs font-semibold text-slate-500">Bundle</dt>
                  <dd className="mt-1 text-base font-bold text-slate-950">
                    {store.bundleMetadata?.downloadBundleVersion ?? "Local fallback"}
                  </dd>
                </div>
                <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
                  <dt className="text-xs font-semibold text-slate-500">Expires</dt>
                  <dd className="mt-1 text-base font-bold text-slate-950">{formatShortDate(store.bundleMetadata?.expiresAt)}</dd>
                </div>
              </dl>
            </section>
          ) : null}
        </section>

        <aside className="grid content-start gap-4">
          <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
            <div className="mb-3 flex items-center justify-between gap-3">
              <h2 className="text-lg font-bold text-slate-950">Offline status</h2>
              {isOnline ? <Cloud className="size-5 text-teal-700" aria-hidden="true" /> : <CloudOff className="size-5 text-amber-700" aria-hidden="true" />}
            </div>
            <div className="grid gap-2 text-sm">
              <div className="flex items-center justify-between gap-3 rounded-lg border border-slate-200 bg-slate-50 p-3">
                <span className="font-semibold text-slate-600">Connection</span>
                <span className="font-bold text-slate-950">{isOnline ? "Online" : "Offline"}</span>
              </div>
              <div className="flex items-center justify-between gap-3 rounded-lg border border-slate-200 bg-slate-50 p-3">
                <span className="font-semibold text-slate-600">Work</span>
                <span className="font-bold text-slate-950">{pendingCount} pending</span>
              </div>
              <div className="flex items-center justify-between gap-3 rounded-lg border border-slate-200 bg-slate-50 p-3">
                <span className="font-semibold text-slate-600">Bundle</span>
                <span className="font-bold text-slate-950">{bundleFreshness?.isStale ? "Stale" : "Ready"}</span>
              </div>
            </div>
          </section>

          <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
            <div className="mb-3 flex items-center gap-2">
              <FileWarning className="size-5 text-amber-700" aria-hidden="true" />
              <h2 className="text-lg font-bold text-slate-950">Next action</h2>
            </div>
            <p className="text-sm font-semibold leading-6 text-slate-700">
              {pendingCount > 0
                ? isOnline
                  ? "Sync pending work."
                  : "Keep pending work saved."
                : selectedTask
                  ? "Open triage."
                  : "Wait for assignment."}
            </p>
            <Button
              size="lg"
              variant={pendingCount > 0 ? "primary" : "secondary"}
              onClick={() => (pendingCount > 0 ? setActiveView("sync") : setActiveView("triage"))}
              className="mt-4 min-h-14 w-full"
            >
              {pendingCount > 0 ? <RefreshCw className="size-5" aria-hidden="true" /> : <HeartPulse className="size-5" aria-hidden="true" />}
              {pendingCount > 0 ? "Open sync" : "Open triage"}
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
          <div className="inline-flex items-center gap-3 text-sm font-semibold text-slate-700">
            <Loader2 className="size-5 animate-spin" aria-hidden="true" />
            Restoring your session
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
