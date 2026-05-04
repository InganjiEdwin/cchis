"use client";

import {
  Activity,
  AlertTriangle,
  ChevronLeft,
  ChevronRight,
  Clock3,
  Filter,
  Search,
  ShieldAlert,
  Smartphone,
  Wifi,
  WifiOff,
  X,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { DashboardTopbar } from "@/components/dashboard-topbar";
import { MigoriWardMap } from "@/components/migori-ward-map";
import { RoleGate } from "@/components/role-gate";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { InputShell } from "@/components/ui/input-shell";
import { StatusBanner } from "@/components/ui/status-banner";
import { StatusBadge } from "@/components/ui/status-badge";
import { cn } from "@/lib/cn";
import type {
  ChvCoverageRequestPriority,
  ChvCoverageRequestRecord,
  ChvOfflineAuditStatus,
  ChvOperationsRecord,
  LatestWardRisk,
  WardMapFeature,
} from "@/lib/dashboard";
import { describeFreshness, formatRelativeTimestamp, getLatestTimestamp } from "@/lib/freshness";
import { useAssignChvCoverageRequestMutation } from "@/queries/use-assign-chv-coverage-request-mutation";
import { useCreateChvMessageMutation } from "@/queries/use-create-chv-message-mutation";
import { useChvMessagesQuery } from "@/queries/use-chv-messages-query";
import { useCreateChvCoverageRequestMutation } from "@/queries/use-create-chv-coverage-request-mutation";
import { useChvCoverageRequestDetailQuery } from "@/queries/use-chv-coverage-request-detail-query";
import { useChvOperationsQuery } from "@/queries/use-chv-operations-query";

type FocusFilter = "ALL" | "HIGH_RISK";
type RegistryStatus = "ACTIVE" | "IDLE" | "OFFLINE";
type RegistryRiskZone = "HIGH" | "MODERATE" | "SAFE";
type SyncHealth = "ONLINE" | "DELAYED" | "OFFLINE";
type QuickFilter = "ALL" | "ACTIVE" | "IDLE" | "OFFLINE" | "HIGH_RISK";
type SelectedWardFilter = "ALL" | `id:${number}`;

type RegistryRow = {
  id: number;
  publicId: string;
  wardId: number;
  initials: string;
  name: string;
  rosterId: string;
  wardName: string;
  status: RegistryStatus;
  alertsRaised: number;
  alertsAcknowledged: number;
  lastSync: string;
  riskZone: RegistryRiskZone;
  syncHealth: SyncHealth;
  phoneNumber: string;
  language: string;
  lastProtocolUpdate: string;
  canMessage: boolean;
  messageMode: "SEND" | "QUEUE_ONLY" | "UNAVAILABLE";
  messageDeliveryKind: "LIVE" | "SIMULATED" | "QUEUE_ONLY" | "UNAVAILABLE";
  canViewActivity: boolean;
};

const ROWS_PER_PAGE = 5;
const STALE_THRESHOLD_MINUTES = 120;

function getInitials(name: string) {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}

function toTitleStatus(status: RegistryStatus) {
  switch (status) {
    case "ACTIVE":
      return "Active";
    case "IDLE":
      return "Idle";
    case "OFFLINE":
    default:
      return "Offline";
  }
}

function toRiskZoneLabel(zone: RegistryRiskZone) {
  switch (zone) {
    case "HIGH":
      return "High risk";
    case "MODERATE":
      return "Watch";
    case "SAFE":
    default:
      return "Safe";
  }
}

function resolveRiskZone(level: string | null | undefined): RegistryRiskZone {
  if (level === "HIGH") {
    return "HIGH";
  }
  if (level === "MEDIUM") {
    return "MODERATE";
  }
  return "SAFE";
}

function normalizeChvMessageMode(chv: ChvOperationsRecord): RegistryRow["messageMode"] {
  if (chv.message_mode === "SEND" || chv.message_mode === "QUEUE_ONLY" || chv.message_mode === "UNAVAILABLE") {
    return chv.message_mode;
  }

  // Older payloads may omit the explicit capability fields. Default to the
  // current real backend flow rather than silently hiding supported actions.
  return "SEND";
}

function normalizeChvMessageDeliveryKind(
  chv: ChvOperationsRecord,
  messageMode: RegistryRow["messageMode"],
): RegistryRow["messageDeliveryKind"] {
  if (
    chv.message_delivery_kind === "LIVE" ||
    chv.message_delivery_kind === "SIMULATED" ||
    chv.message_delivery_kind === "QUEUE_ONLY" ||
    chv.message_delivery_kind === "UNAVAILABLE"
  ) {
    return chv.message_delivery_kind;
  }

  if (messageMode === "QUEUE_ONLY") {
    return "QUEUE_ONLY";
  }
  if (messageMode === "UNAVAILABLE") {
    return "UNAVAILABLE";
  }
  return "SIMULATED";
}

function normalizeChvCapabilities(chv: ChvOperationsRecord) {
  const messageMode = normalizeChvMessageMode(chv);
  const messageDeliveryKind = normalizeChvMessageDeliveryKind(chv, messageMode);
  const canMessage =
    typeof chv.can_message === "boolean"
      ? chv.can_message
      : messageMode === "SEND" || messageMode === "QUEUE_ONLY";
  const canViewActivity = typeof chv.can_view_activity === "boolean" ? chv.can_view_activity : Boolean(chv.public_id);

  return {
    canMessage,
    canViewActivity,
    messageMode,
    messageDeliveryKind,
  };
}

function toSyncHealthLabel(syncHealth: SyncHealth) {
  switch (syncHealth) {
    case "ONLINE":
      return "Online";
    case "DELAYED":
      return "Delayed sync";
    case "OFFLINE":
    default:
      return "Offline";
  }
}

function statusTone(status: RegistryStatus) {
  switch (status) {
    case "ACTIVE":
      return "success" as const;
    case "IDLE":
      return "warning" as const;
    case "OFFLINE":
    default:
      return "default" as const;
  }
}

function riskTone(zone: RegistryRiskZone) {
  switch (zone) {
    case "HIGH":
      return "danger" as const;
    case "MODERATE":
      return "warning" as const;
    case "SAFE":
    default:
      return "success" as const;
  }
}

function syncTone(sync: SyncHealth) {
  switch (sync) {
    case "ONLINE":
      return "success" as const;
    case "DELAYED":
      return "warning" as const;
    case "OFFLINE":
    default:
      return "default" as const;
  }
}

function auditStatusTone(status: ChvOfflineAuditStatus) {
  switch (status) {
    case "PASS":
      return "success" as const;
    case "FAIL":
      return "danger" as const;
    case "WARN":
    default:
      return "warning" as const;
  }
}

function formatLatency(minutes: number | null | undefined) {
  if (typeof minutes !== "number") {
    return "No data";
  }
  if (minutes < 60) {
    return `${minutes.toLocaleString()} min`;
  }
  return `${(minutes / 60).toFixed(1)} hr`;
}

function getCoverageStatus(feature: WardMapFeature) {
  if (!feature.properties.has_backend_ward) {
    return {
      label: "Unmatched",
      tone: "default" as const,
      reason: "Geometry exists locally, but no backend ward row is matched yet.",
    };
  }

  const active = feature.properties.active_chv_count;
  const total = feature.properties.chv_count;
  const riskLevel = feature.properties.risk_level;

  if (active === 0) {
    return {
      label: "Gap",
      tone: "danger" as const,
      reason: "0 active CHVs are recorded in this ward.",
    };
  }

  if (riskLevel === "HIGH" && active <= 1) {
    return {
      label: "Gap",
      tone: "danger" as const,
      reason: "High recorded risk is paired with only 1 active CHV.",
    };
  }

  if ((riskLevel === "HIGH" && active <= 2) || (riskLevel === "MEDIUM" && active <= 1)) {
    return {
      label: "Low",
      tone: "warning" as const,
      reason: "Recorded risk is elevated relative to the visible active CHV count.",
      action: "Monitor staffing",
    };
  }

  if (total > 0 && active / total < 0.5) {
    return {
      label: "Low",
      tone: "warning" as const,
      reason: "Less than half of linked CHVs are active in this ward.",
      action: "Stabilize activity",
    };
  }

  return {
    label: "Good",
    tone: "success" as const,
    reason: "Active CHV coverage is present for the current recorded ward risk.",
    action: "Maintain coverage",
  };
}

function isLiveCoverageRequestStatus(status: ChvCoverageRequestRecord["status"]) {
  return status === "OPEN" || status === "APPROVED" || status === "IN_PROGRESS";
}

function hasStoredAlertLinkage(requestRecord: Pick<ChvCoverageRequestRecord, "trigger_source" | "linked_alerts_summary">) {
  return requestRecord.trigger_source === "ALERT_DRIVEN" && requestRecord.linked_alerts_summary.length > 0;
}

function hasLinkedAlertContext(requestRecord: Pick<ChvCoverageRequestRecord, "linked_alerts_summary">) {
  return requestRecord.linked_alerts_summary.length > 0;
}

function getCoverageRequestSourceDescription(
  requestRecord: Pick<ChvCoverageRequestRecord, "trigger_source" | "linked_alerts_summary">,
) {
  if (hasStoredAlertLinkage(requestRecord)) {
    return "This request was opened from alert context.";
  }
  if (hasLinkedAlertContext(requestRecord)) {
    return "This request was opened manually and later linked to alert context.";
  }
  return "This request was opened without stored alert-linked context.";
}

function getCoverageRequestStatusLabel(status: ChvCoverageRequestRecord["status"]) {
  switch (status) {
    case "OPEN":
      return "Coverage request open";
    case "APPROVED":
      return "Coverage approved";
    case "IN_PROGRESS":
      return "Assignment in progress";
    case "REJECTED":
      return "Coverage request rejected";
    case "RESOLVED":
      return "Coverage request resolved";
    case "CANCELLED":
    default:
      return "Coverage request cancelled";
  }
}

function getCoverageRequestStatusMessage(requestRecord: ChvCoverageRequestRecord) {
  switch (requestRecord.status) {
    case "OPEN":
      return "This ward already has a live request pending review, so the next truthful action is to track that request instead of opening another one.";
    case "APPROVED":
      return "Coverage follow-up has been approved. The next truthful action is to review the request and watch assignment progress.";
    case "IN_PROGRESS":
      return "Assignment work is active for this ward, so the next truthful action is to review request progress instead of opening another request.";
    case "REJECTED":
      return "The latest request was rejected. Review the recorded reason before opening a new request.";
    case "RESOLVED":
      return "The latest request is resolved. Open a new request only if coverage conditions have changed again.";
    case "CANCELLED":
    default:
      return "The latest request was cancelled. Review it before deciding whether to reopen the issue.";
  }
}

function getDefaultCoverageRequestPriority(feature: WardMapFeature): ChvCoverageRequestPriority {
  if (feature.properties.active_chv_count === 0 && feature.properties.risk_level === "HIGH") {
    return "HIGH";
  }
  if (feature.properties.active_chv_count === 0) {
    return "MEDIUM";
  }
  return feature.properties.risk_level === "HIGH" ? "MEDIUM" : "LOW";
}

function getPrefilledCoverageRequestReason(feature: WardMapFeature) {
  if (feature.properties.active_chv_count === 0) {
    return "Coverage gap detected: 0 active CHVs recorded in this ward.";
  }

  return `Coverage threshold concern detected: ${feature.properties.active_chv_count} active CHV${feature.properties.active_chv_count === 1 ? "" : "s"} recorded in this ward for the current risk profile.`;
}

function buildChvMessageTemplates(chvName: string, wardName: string) {
  return [
    {
      label: "Check in",
      body: `Hello ${chvName}, please check in when you are able and confirm your current field status in ${wardName}.`,
    },
    {
      label: "Coverage follow-up",
      body: `Hello ${chvName}, please review the current coverage situation in ${wardName} and confirm whether follow-up support is needed.`,
    },
    {
      label: "Alert follow-up",
      body: `Hello ${chvName}, please follow up on the latest alert context in ${wardName} and share any field update you have.`,
    },
  ] as const;
}

function getChvMessageCapabilityLabel(messageMode: RegistryRow["messageMode"], deliveryKind: RegistryRow["messageDeliveryKind"]) {
  if (messageMode === "QUEUE_ONLY" || deliveryKind === "QUEUE_ONLY") {
    return "Messages from this screen are queued only.";
  }
  if (deliveryKind === "SIMULATED") {
    return "Test-mode SMS send is available from this screen.";
  }
  if (deliveryKind === "LIVE") {
    return "Live SMS send is available from this screen.";
  }
  return "Messaging is not available from this screen.";
}

function getChvMessageDeliveryTag(deliveryKind: "LIVE" | "SIMULATED" | "QUEUE_ONLY" | "UNAVAILABLE") {
  if (deliveryKind === "LIVE") return "Live delivery";
  if (deliveryKind === "SIMULATED") return "Test mode";
  if (deliveryKind === "QUEUE_ONLY") return "Queued only";
  return "Unavailable";
}

export default function ChvsPage() {
  const { currentUser } = useAuth();
  const [search, setSearch] = useState("");
  const [selectedWard, setSelectedWard] = useState<SelectedWardFilter>("ALL");
  const [focusFilter, setFocusFilter] = useState<FocusFilter>("ALL");
  const [quickFilter, setQuickFilter] = useState<QuickFilter>("ALL");
  const [currentPage, setCurrentPage] = useState(1);
  const [selectedChvId, setSelectedChvId] = useState<number | null>(null);
  const [isChvMessageModalOpen, setIsChvMessageModalOpen] = useState(false);
  const [selectedMessageTemplateLabel, setSelectedMessageTemplateLabel] = useState<string | null>(null);
  const [messageBody, setMessageBody] = useState("");
  const [messageFeedback, setMessageFeedback] = useState<string | null>(null);
  const [isCoverageRequestModalOpen, setIsCoverageRequestModalOpen] = useState(false);
  const [selectedCoverageRequestId, setSelectedCoverageRequestId] = useState<string | null>(null);
  const [requestPriority, setRequestPriority] = useState<ChvCoverageRequestPriority>("MEDIUM");
  const [requestCount, setRequestCount] = useState(1);
  const [requestReason, setRequestReason] = useState("");
  const [requestNotes, setRequestNotes] = useState("");
  const [requestFeedback, setRequestFeedback] = useState<string | null>(null);
  const [assignmentChvId, setAssignmentChvId] = useState<number | null>(null);
  const [assignmentNotes, setAssignmentNotes] = useState("");
  const { data, isPending: isLoading, error } = useChvOperationsQuery({
    enabled: Boolean(currentUser),
  });
  const createCoverageRequestMutation = useCreateChvCoverageRequestMutation();
  const assignCoverageRequestMutation = useAssignChvCoverageRequestMutation();
  const chvs = data?.chvs ?? [];
  const latestRisks = data?.latestRisks ?? [];
  const alerts = data?.alerts ?? [];
  const wardMap = data?.wardMap ?? null;
  const coverageRequests = data?.coverageRequests ?? [];
  const coverageByWard = data?.coverageByWard ?? {};
  const offlineMonitoring = data?.offlineMonitoring ?? null;
  const offlineMetrics = offlineMonitoring?.metrics ?? null;
  const offlineAuditChecks = offlineMonitoring?.audit_checks ?? [];
  const offlineSyncHealthByWard = offlineMonitoring?.sync_health_by_ward ?? [];
  const recentSyncDecisions = offlineMonitoring?.recent_sync_decisions ?? [];
  const recentRejectedSubmissionAudits = offlineMonitoring?.recent_rejected_submission_audits ?? [];
  const mapFeatures = wardMap?.features ?? [];

  const latestTimestamp = useMemo(
    () =>
      getLatestTimestamp([
        ...chvs.flatMap((item) => [item.created_at, item.last_activity_at, item.last_sync_at].filter(Boolean)),
        ...latestRisks.map((item) => item.generated_at),
        ...alerts.map((item) => item.created_at),
        offlineMonitoring?.generated_at,
      ]),
    [alerts, chvs, latestRisks, offlineMonitoring],
  );

  const freshness = useMemo(
    () => describeFreshness(latestTimestamp, STALE_THRESHOLD_MINUTES),
    [latestTimestamp],
  );
  const lastUpdatedLabel = latestTimestamp ? formatRelativeTimestamp(latestTimestamp) : freshness.label;

  const riskByWard = useMemo(() => {
    const map = new Map<number, LatestWardRisk>();
    latestRisks.forEach((risk) => {
      map.set(risk.ward_id, risk);
    });
    return map;
  }, [latestRisks]);

  const wardsForFilter = useMemo(() => {
    const options = new Map<string, string>();
    options.set("ALL", "All Wards");

    mapFeatures.forEach((feature) => {
      if (feature.properties.backend_ward_id) {
        options.set(`id:${feature.properties.backend_ward_id}`, feature.properties.name);
      }
    });

    chvs.forEach((chv) => {
      options.set(`id:${chv.ward}`, chv.ward_name);
    });

    return [...options.entries()]
      .map(([value, label]) => ({ value, label }))
      .sort((left, right) => {
        if (left.value === "ALL") return -1;
        if (right.value === "ALL") return 1;
        return left.label.localeCompare(right.label);
      });
  }, [chvs, mapFeatures]);

  const filteredChvs = useMemo(() => {
    const normalizedSearch = search.trim().toLowerCase();

    return chvs.filter((chv) => {
      if (selectedWard !== "ALL") {
        if (chv.ward !== Number(selectedWard.slice(3))) {
          return false;
        }
      }

      const riskLevel = riskByWard.get(chv.ward)?.risk_level ?? "LOW";
      if (focusFilter === "HIGH_RISK" && riskLevel !== "HIGH") {
        return false;
      }

      const status = chv.operational_status;
      if (quickFilter === "ACTIVE" && status !== "ACTIVE") return false;
      if (quickFilter === "IDLE" && status !== "IDLE") return false;
      if (quickFilter === "OFFLINE" && status !== "OFFLINE") return false;
      if (quickFilter === "HIGH_RISK" && riskLevel !== "HIGH") return false;

      if (!normalizedSearch) {
        return true;
      }

      return (
        chv.name.toLowerCase().includes(normalizedSearch) ||
        chv.phone_number.toLowerCase().includes(normalizedSearch) ||
        chv.ward_name.toLowerCase().includes(normalizedSearch)
      );
    });
  }, [chvs, focusFilter, quickFilter, riskByWard, search, selectedWard]);

  useEffect(() => {
    setCurrentPage(1);
  }, [focusFilter, quickFilter, search, selectedWard]);

  const activeChvs = filteredChvs.filter((item) => item.operational_status === "ACTIVE").length;
  const highUrgencyCases = filteredChvs.reduce((sum, item) => sum + item.triage_sessions_24h, 0);

  const registryRows = useMemo<RegistryRow[]>(() => {
    return filteredChvs.map((chv) => {
      const capabilities = normalizeChvCapabilities(chv);
      return {
        id: chv.id,
        publicId: chv.public_id,
        wardId: chv.ward,
        initials: getInitials(chv.name),
        name: chv.name,
        rosterId: `Phone ${chv.phone_number}`,
        wardName: chv.ward_name,
        status: chv.operational_status,
        alertsRaised: chv.ward_alerts_total,
        alertsAcknowledged: chv.ward_alerts_delivered,
        lastSync: chv.last_sync_at ? formatRelativeTimestamp(chv.last_sync_at) : "No sync recorded",
        riskZone: resolveRiskZone(riskByWard.get(chv.ward)?.risk_level),
        syncHealth: chv.sync_health,
        phoneNumber: chv.phone_number,
        language: chv.language,
        lastProtocolUpdate: chv.last_activity_at ? formatRelativeTimestamp(chv.last_activity_at) : "No recent activity",
        canMessage: capabilities.canMessage,
        messageMode: capabilities.messageMode,
        messageDeliveryKind: capabilities.messageDeliveryKind,
        canViewActivity: capabilities.canViewActivity,
      };
    });
  }, [filteredChvs, riskByWard]);

  const selectedChv = useMemo(
    () => registryRows.find((row) => row.id === selectedChvId) ?? null,
    [registryRows, selectedChvId],
  );
  const {
    data: chvMessages = [],
    isPending: isChvMessagesPending,
    error: chvMessagesError,
  } = useChvMessagesQuery(selectedChv?.publicId ?? null, {
    enabled: Boolean(selectedChv?.canMessage && isChvMessageModalOpen),
  });
  const createChvMessageMutation = useCreateChvMessageMutation(selectedChv?.publicId ?? null);

  useEffect(() => {
    setIsChvMessageModalOpen(false);
    setSelectedMessageTemplateLabel(null);
    setMessageBody("");
    setMessageFeedback(null);
  }, [selectedChvId]);
  const latestChvMessage = chvMessages[0] ?? null;
  const selectedChvMessageTemplates = selectedChv ? buildChvMessageTemplates(selectedChv.name, selectedChv.wardName) : [];

  const totalPages = Math.max(1, Math.ceil(registryRows.length / ROWS_PER_PAGE));
  const clampedPage = Math.min(currentPage, totalPages);
  const pagedRows = registryRows.slice((clampedPage - 1) * ROWS_PER_PAGE, clampedPage * ROWS_PER_PAGE);

  const highPriorityReferrals = latestRisks
    .filter((item) => item.risk_level === "HIGH")
    .reduce(
      (sum, item) =>
        sum +
        filteredChvs
          .filter((chv) => chv.ward === item.ward_id)
          .reduce((chvSum, chv) => chvSum + chv.referrals_24h, 0),
      0,
    );
  const delayedOrOfflineCount = registryRows.filter((row) => row.syncHealth !== "ONLINE").length;
  const offlineAuditIssueCount = offlineAuditChecks.filter((check) => check.status !== "PASS").length;
  const latestRejectedSyncDecision = recentSyncDecisions.find((decision) => decision.decision === "REJECTED") ?? null;
  const latestPreValidationRejection = recentRejectedSubmissionAudits[0] ?? null;
  const visibleOfflineSyncRows = selectedWard === "ALL"
    ? offlineSyncHealthByWard.slice(0, 4)
    : offlineSyncHealthByWard.filter((row) => row.ward_id === Number(selectedWard.slice(3))).slice(0, 4);
  const totalVisibleLabel = isLoading ? "..." : filteredChvs.length.toLocaleString();
  const activeVisibleLabel = isLoading ? "..." : activeChvs.toLocaleString();
  const casesVisibleLabel = isLoading ? "..." : highUrgencyCases.toLocaleString();
  const selectedMapWard = useMemo<WardMapFeature | null>(() => {
    if (!mapFeatures.length) {
      return null;
    }

    if (selectedWard !== "ALL") {
      return mapFeatures.find((feature) => feature.properties.backend_ward_id === Number(selectedWard.slice(3))) ?? null;
    }

    const highestPriority = mapFeatures
      .filter((feature) => feature.properties.risk_level === "HIGH")
      .sort((left, right) => right.properties.predicted_cases - left.properties.predicted_cases)[0];

    return highestPriority ?? mapFeatures[0];
  }, [mapFeatures, selectedWard]);
  const selectedWardCoverage = useMemo(
    () => (selectedMapWard ? getCoverageStatus(selectedMapWard) : null),
    [selectedMapWard],
  );
  const selectedWardRecords = useMemo(
    () =>
      selectedMapWard?.properties.backend_ward_id
        ? chvs.filter((chv) => chv.ward === selectedMapWard.properties.backend_ward_id)
        : [],
    [chvs, selectedMapWard],
  );
  const selectedWardLatestActivity = useMemo(
    () => getLatestTimestamp(selectedWardRecords.map((item) => item.last_activity_at).filter(Boolean)),
    [selectedWardRecords],
  );
  const selectedWardLatestSync = useMemo(
    () => getLatestTimestamp(selectedWardRecords.map((item) => item.last_sync_at).filter(Boolean)),
    [selectedWardRecords],
  );
  const selectedWardSyncFreshness = useMemo(
    () => describeFreshness(selectedWardLatestSync, STALE_THRESHOLD_MINUTES),
    [selectedWardLatestSync],
  );
  const selectedWardRiskLabel = selectedMapWard?.properties.risk_level
    ? toRiskZoneLabel(resolveRiskZone(selectedMapWard.properties.risk_level))
    : "No backend risk";
  const selectedWardPanelTone = selectedWardCoverage?.tone ?? "default";
  const selectedWardPanelClassName =
    selectedWardPanelTone === "danger"
      ? "border-[color:var(--danger)]/25 bg-[linear-gradient(180deg,color-mix(in_srgb,var(--danger)_8%,var(--panel)),var(--panel))]"
      : selectedWardPanelTone === "warning"
        ? "border-[color:var(--warning)]/28 bg-[linear-gradient(180deg,color-mix(in_srgb,var(--warning)_9%,var(--panel)),var(--panel))]"
        : selectedWardPanelTone === "success"
          ? "border-[color:var(--success)]/24 bg-[linear-gradient(180deg,color-mix(in_srgb,var(--success)_8%,var(--panel)),var(--panel))]"
          : "border-panel-table-wrap bg-panel";
  const coverageSummary = useMemo(() => {
    const counts = {
      gap: 0,
      low: 0,
      good: 0,
      noData: 0,
    };

    const priorities: Array<{
      name: string;
      activeChvs: number;
      predictedCases: number;
      tone: "gap" | "low";
    }> = [];

    mapFeatures.forEach((feature) => {
      const coverage = getCoverageStatus(feature);

      if (coverage.label === "Gap") counts.gap += 1;
      else if (coverage.label === "Low") counts.low += 1;
      else if (coverage.label === "Good") counts.good += 1;
      else counts.noData += 1;

      if (coverage.label === "Gap" || coverage.label === "Low") {
        priorities.push({
          name: feature.properties.name,
          activeChvs: feature.properties.active_chv_count,
          predictedCases: feature.properties.predicted_cases,
          tone: coverage.label === "Gap" ? "gap" : "low",
        });
      }
    });

    priorities.sort((left, right) => {
      if (left.tone !== right.tone) {
        return left.tone === "gap" ? -1 : 1;
      }

      if (left.activeChvs !== right.activeChvs) {
        return left.activeChvs - right.activeChvs;
      }

      return right.predictedCases - left.predictedCases;
    });

    return {
      ...counts,
      priorities: priorities.slice(0, 3),
    };
  }, [mapFeatures]);
  const selectedWardId =
    selectedWard !== "ALL" ? Number(selectedWard.slice(3)) : selectedMapWard?.properties.backend_ward_id ?? null;
  const selectedWardWorkflowSummary = selectedWardId ? coverageByWard[selectedWardId] ?? null : null;
  const selectedWardLiveRequest =
    selectedWardWorkflowSummary?.latestRequest && isLiveCoverageRequestStatus(selectedWardWorkflowSummary.latestRequest.status)
      ? selectedWardWorkflowSummary.latestRequest
      : null;
  const canRequestCoverageFromSelectedWard = Boolean(
    selectedMapWard && selectedWardCoverage?.label === "Gap" && !selectedWardLiveRequest,
  );
  const canAssignChvFromSelectedWard = selectedWardLiveRequest?.status === "APPROVED";
  const selectedWardAlertsHref = selectedWardId ? `/alerts?ward_id=${selectedWardId}` : "/alerts";
  const selectedWardPrimaryActionLabel = selectedWardLiveRequest
    ? selectedWardLiveRequest.status === "OPEN"
      ? "Track pending coverage request"
      : selectedWardLiveRequest.status === "APPROVED"
        ? "Assign CHV"
        : "Review active request"
    : canRequestCoverageFromSelectedWard
      ? "Request coverage"
      : selectedWardCoverage?.action ?? "Review ward coverage";
  const selectedWardPrimaryActionDetail = selectedWardLiveRequest
    ? `Latest request priority: ${selectedWardLiveRequest.priority}. Requested by ${selectedWardLiveRequest.requested_by_username ?? "system"} on ${formatRelativeTimestamp(selectedWardLiveRequest.created_at)}.`
    : canRequestCoverageFromSelectedWard
      ? "No active CHVs are visible here, so coverage follow-up should start with a real request."
      : selectedWardCoverage?.label === "Low"
        ? "Coverage is below the visible threshold for this ward's current risk."
        : "Coverage is present, so monitor activity and review alerts before changing staffing.";
  const selectedCoverageRequest = useMemo(
    () =>
      selectedCoverageRequestId
        ? coverageRequests.find((requestRecord) => requestRecord.public_id === selectedCoverageRequestId) ?? null
        : null,
    [coverageRequests, selectedCoverageRequestId],
  );
  const selectedCoverageRequestDetailQuery = useChvCoverageRequestDetailQuery({
    publicId: selectedCoverageRequestId,
    enabled: Boolean(selectedCoverageRequestId),
  });
  const selectedCoverageRequestDetail = selectedCoverageRequestDetailQuery.data ?? selectedCoverageRequest;
  const hasFreshSelectedCoverageRequestDetail = Boolean(selectedCoverageRequestDetailQuery.data);
  const selectedWardName =
    selectedMapWard?.properties.name ??
    wardsForFilter.find((option) => option.value === selectedWard)?.label ??
    null;
  const filteredWardAlertCount = useMemo(() => {
    if (!selectedWardId) {
      return 0;
    }

    return alerts.filter((item) => item.ward === selectedWardId).length;
  }, [alerts, selectedWardId]);
  const operationalInsights = [
    coverageSummary.gap > 0
      ? `${coverageSummary.gap} ward${coverageSummary.gap === 1 ? "" : "s"} have no active CHV coverage in visible records.`
      : "No visible wards are completely uncovered by active CHVs.",
    delayedOrOfflineCount > 0
      ? `${delayedOrOfflineCount} CHV${delayedOrOfflineCount === 1 ? "" : "s"} show delayed sync or offline status in the current view.`
      : "No visible CHVs are currently flagged for delayed sync or offline status.",
    highUrgencyCases > 0
      ? `${highUrgencyCases} triage session${highUrgencyCases === 1 ? "" : "s"} were recorded in the last 24 hours.`
      : "No triage sessions were recorded in the visible scope during the last 24 hours.",
    offlineMetrics
      ? `${offlineMetrics.pending_uploads.toLocaleString()} pending offline upload${offlineMetrics.pending_uploads === 1 ? "" : "s"}, ${offlineMetrics.failed_syncs_24h.toLocaleString()} failed sync${offlineMetrics.failed_syncs_24h === 1 ? "" : "s"}, and ${offlineMetrics.pre_validation_rejections_24h.toLocaleString()} pre-validation reject${offlineMetrics.pre_validation_rejections_24h === 1 ? "" : "s"} were recorded in the monitoring window.`
      : "Offline sync monitoring is not available for the visible scope yet.",
  ];

  useEffect(() => {
    if (!selectedMapWard) {
      return;
    }

    setRequestPriority(getDefaultCoverageRequestPriority(selectedMapWard));
    setRequestCount(1);
    setRequestReason(getPrefilledCoverageRequestReason(selectedMapWard));
    setRequestNotes("");
  }, [selectedMapWard]);

  const assignableWardChvs = useMemo(() => {
    if (!selectedCoverageRequestDetail) {
      return [];
    }

    return chvs.filter(
      (chv) =>
        chv.ward === selectedCoverageRequestDetail.ward &&
        chv.is_active &&
        chv.operational_status !== "OFFLINE",
    );
  }, [chvs, selectedCoverageRequestDetail]);

  useEffect(() => {
    if (!selectedCoverageRequestDetail || selectedCoverageRequestDetail.status !== "APPROVED") {
      setAssignmentChvId(null);
      setAssignmentNotes("");
      return;
    }

    const firstCandidate = assignableWardChvs[0];
    setAssignmentChvId(firstCandidate?.id ?? null);
    setAssignmentNotes("");
  }, [assignableWardChvs, selectedCoverageRequestDetail]);

  if (!currentUser) {
    return null;
  }

  return (
    <div className="space-y-6">
      <DashboardTopbar
        title="Community Health Volunteers"
        subtitle="CHV activity summaries, sync status, and ward-linked engagement data"
        lastUpdatedLabel={lastUpdatedLabel}
        lastUpdatedTone={freshness.isStale ? "stale" : "default"}
      />

      <RoleGate
        allowedRoles={["ADMIN", "SUPERVISOR"]}
        title="CHV operations are role-restricted"
        message="Only Admin and Supervisor roles should use the CHV operations page."
      >
        {error ? (
          <StatusBanner tone="danger" icon={<AlertTriangle aria-hidden="true" />}>
            {error instanceof Error ? error.message : "Unable to load CHV operations."}
          </StatusBanner>
        ) : null}
        {requestFeedback ? <StatusBanner tone="success">{requestFeedback}</StatusBanner> : null}

        <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <Card className="rounded-[2rem] px-5 py-5">
            <span className="text-xs font-semibold uppercase tracking-[0.18em] text-panel-subtle">Visible CHVs</span>
            <div className="mt-3 text-4xl font-semibold leading-none text-panel-strong">{totalVisibleLabel}</div>
            <p className="mt-4 text-sm text-panel-muted">Visible in the selected ward filter</p>
          </Card>

          <Card className="rounded-[2rem] px-5 py-5">
            <span className="text-xs font-semibold uppercase tracking-[0.18em] text-panel-subtle">Active today</span>
            <div className="mt-3 flex items-end gap-2">
              <strong className="text-4xl font-semibold leading-none text-panel-strong">{activeVisibleLabel}</strong>
              <span className="pb-1 text-sm font-medium text-panel-muted">/ {totalVisibleLabel}</span>
            </div>
            <p className="mt-4 text-sm text-panel-muted">CHVs marked active in the current visible scope</p>
          </Card>

          <Card className="rounded-[2rem] px-5 py-5">
            <span className="text-xs font-semibold uppercase tracking-[0.18em] text-panel-subtle">Coverage gaps</span>
            <div className="mt-3 flex items-center gap-3">
              <strong className="text-4xl font-semibold leading-none text-panel-strong">{coverageSummary.gap}</strong>
              <StatusBadge tone={coverageSummary.gap > 0 ? "danger" : "success"} className="tracking-[0.12em]">
                {coverageSummary.gap > 0 ? "Needs action" : "Stable"}
              </StatusBadge>
            </div>
            <p className="mt-4 text-sm text-panel-muted">Wards with no active CHV coverage in the visible map scope</p>
          </Card>

          <Card className="rounded-[2rem] px-5 py-5">
            <span className="text-xs font-semibold uppercase tracking-[0.18em] text-panel-subtle">
              Recorded triage sessions (24h)
            </span>
            <div className="mt-3 text-4xl font-semibold leading-none text-panel-strong">{casesVisibleLabel}</div>
            <p className="mt-4 text-sm text-panel-muted">{highPriorityReferrals.toLocaleString()} referrals in high-risk wards (calculated)</p>
          </Card>
        </section>

        <section className="grid gap-5 xl:grid-cols-[minmax(0,1.05fr)_minmax(22rem,0.95fr)]">
          <Card className="rounded-[2rem] px-5 py-5 sm:px-6">
            <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <h2 className="text-2xl font-semibold text-panel-strong">Offline Sync Health</h2>
                <p className="mt-2 text-sm text-panel-muted">
                  Device activity, queued uploads, conflicts, and ward-level sync freshness
                </p>
              </div>
              <span className="inline-flex size-11 items-center justify-center rounded-full bg-[color-mix(in_srgb,var(--brand)_12%,white)] text-brand dark:bg-[color-mix(in_srgb,var(--brand)_20%,transparent)]">
                <Smartphone className="size-5" aria-hidden="true" />
              </span>
            </div>

            <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              {[
                {
                  label: "Active devices",
                  value: offlineMetrics ? offlineMetrics.active_chv_devices.toLocaleString() : "...",
                  detail: offlineMetrics ? `${offlineMetrics.registered_chv_devices.toLocaleString()} registered` : "Loading",
                  icon: <Smartphone className="size-4" aria-hidden="true" />,
                },
                {
                  label: "Successful syncs (24h)",
                  value: offlineMetrics ? offlineMetrics.successful_syncs_24h.toLocaleString() : "...",
                  detail: "Accepted uploads",
                  icon: <Wifi className="size-4" aria-hidden="true" />,
                },
                {
                  label: "Failed syncs (24h)",
                  value: offlineMetrics ? offlineMetrics.failed_syncs_24h.toLocaleString() : "...",
                  detail: "Rejected uploads",
                  icon: <WifiOff className="size-4" aria-hidden="true" />,
                },
                {
                  label: "Avg task latency",
                  value: offlineMetrics ? formatLatency(offlineMetrics.offline_task_completion_latency_minutes) : "...",
                  detail: "Offline completion",
                  icon: <Clock3 className="size-4" aria-hidden="true" />,
                },
              ].map((metric) => (
                <div
                  key={metric.label}
                  className="rounded-[1.25rem] border border-panel-table-wrap bg-[color-mix(in_srgb,var(--dashboard-icon-button-surface)_76%,transparent)] px-4 py-3"
                >
                  <div className="flex items-center justify-between gap-3 text-panel-muted">
                    <span className="text-[11px] font-semibold uppercase tracking-[0.14em] text-panel-subtle">
                      {metric.label}
                    </span>
                    {metric.icon}
                  </div>
                  <strong className="mt-3 block text-2xl font-semibold text-panel-strong">{metric.value}</strong>
                  <p className="mt-1 text-xs text-panel-muted">{metric.detail}</p>
                </div>
              ))}
            </div>

            <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <div className="rounded-[1.25rem] border border-panel-table-wrap px-4 py-3 text-sm">
                <span className="block text-[11px] font-semibold uppercase tracking-[0.14em] text-panel-subtle">Pending uploads</span>
                <strong className="mt-2 block text-xl text-panel-strong">
                  {offlineMetrics ? offlineMetrics.pending_uploads.toLocaleString() : "..."}
                </strong>
              </div>
              <div className="rounded-[1.25rem] border border-panel-table-wrap px-4 py-3 text-sm">
                <span className="block text-[11px] font-semibold uppercase tracking-[0.14em] text-panel-subtle">Stale bundles</span>
                <strong className="mt-2 block text-xl text-panel-strong">
                  {offlineMetrics ? offlineMetrics.stale_guidance_bundles.toLocaleString() : "..."}
                </strong>
              </div>
              <div className="rounded-[1.25rem] border border-panel-table-wrap px-4 py-3 text-sm">
                <span className="block text-[11px] font-semibold uppercase tracking-[0.14em] text-panel-subtle">Pre-validation rejects</span>
                <strong className="mt-2 block text-xl text-panel-strong">
                  {offlineMetrics ? offlineMetrics.pre_validation_rejections_24h.toLocaleString() : "..."}
                </strong>
              </div>
              <div className="rounded-[1.25rem] border border-panel-table-wrap px-4 py-3 text-sm">
                <span className="block text-[11px] font-semibold uppercase tracking-[0.14em] text-panel-subtle">Conflicts (7d)</span>
                <strong className="mt-2 block text-xl text-panel-strong">
                  {offlineMetrics ? offlineMetrics.conflict_count_7d.toLocaleString() : "..."}
                </strong>
              </div>
            </div>

            <div className="mt-5 space-y-3">
              {visibleOfflineSyncRows.length ? (
                visibleOfflineSyncRows.map((row) => (
                  <div
                    key={row.ward_id}
                    className="flex flex-col gap-3 rounded-[1.25rem] border border-panel-table-wrap bg-[color-mix(in_srgb,var(--dashboard-icon-button-surface)_70%,transparent)] px-4 py-3 sm:flex-row sm:items-center sm:justify-between"
                  >
                    <div>
                      <strong className="text-sm text-panel-strong">{row.ward_name}</strong>
                      <p className="mt-1 text-xs text-panel-muted">
                        {row.active_device_count}/{row.registered_device_count} active devices, {row.pending_upload_count} pending uploads, {row.pre_validation_rejection_count_24h} pre-validation rejects
                      </p>
                    </div>
                    <StatusBadge tone={syncTone(row.sync_health)}>{toSyncHealthLabel(row.sync_health)}</StatusBadge>
                  </div>
                ))
              ) : (
                <div className="rounded-[1.25rem] border border-dashed border-panel-table-wrap px-4 py-4 text-sm text-panel-muted">
                  No ward sync health rows are available for this scope.
                </div>
              )}
            </div>
          </Card>

          <Card className="rounded-[2rem] px-5 py-5 sm:px-6">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h2 className="text-2xl font-semibold text-panel-strong">Offline Sync Audit</h2>
                <p className="mt-2 text-sm text-panel-muted">
                  Accepted and rejected submissions grouped by assignment, bundle, and linkage checks
                </p>
              </div>
              <StatusBadge tone={offlineAuditIssueCount ? "warning" : "success"}>
                {offlineAuditIssueCount ? `${offlineAuditIssueCount} flagged` : "Clear"}
              </StatusBadge>
            </div>

            <div className="mt-5 space-y-3">
              {offlineAuditChecks.length ? (
                offlineAuditChecks.map((check) => (
                  <div
                    key={check.key}
                    className="rounded-[1.25rem] border border-panel-table-wrap bg-[color-mix(in_srgb,var(--dashboard-icon-button-surface)_76%,transparent)] px-4 py-3"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <strong className="text-sm text-panel-strong">{check.title}</strong>
                        <p className="mt-1 text-xs leading-5 text-panel-muted">{check.summary}</p>
                      </div>
                      <StatusBadge tone={auditStatusTone(check.status)}>{check.status}</StatusBadge>
                    </div>
                    <div className="mt-3 flex items-center gap-2 text-xs text-panel-subtle">
                      <Activity className="size-3.5" aria-hidden="true" />
                      <span>{check.count.toLocaleString()} record{check.count === 1 ? "" : "s"}</span>
                    </div>
                  </div>
                ))
              ) : (
                <div className="rounded-[1.25rem] border border-dashed border-panel-table-wrap px-4 py-4 text-sm text-panel-muted">
                  No audit checks are available for this scope.
                </div>
              )}
            </div>

            <div className="mt-5 rounded-[1.25rem] border border-panel-table-wrap bg-panel px-4 py-4">
              <span className="text-[11px] font-semibold uppercase tracking-[0.16em] text-panel-subtle">Latest backend decision</span>
              {recentSyncDecisions[0] ? (
                <div className="mt-3 space-y-2">
                  <div className="flex items-center justify-between gap-3">
                    <strong className="text-sm text-panel-strong">{recentSyncDecisions[0].upload_type}</strong>
                    <StatusBadge tone={recentSyncDecisions[0].decision === "ACCEPTED" ? "success" : recentSyncDecisions[0].decision === "REJECTED" ? "danger" : "warning"}>
                      {recentSyncDecisions[0].decision}
                    </StatusBadge>
                  </div>
                  <p className="text-sm leading-6 text-panel-copy">{recentSyncDecisions[0].explanation}</p>
                  {latestRejectedSyncDecision ? (
                    <p className="text-xs leading-5 text-panel-muted">
                      Latest rejection: {latestRejectedSyncDecision.explanation}
                    </p>
                  ) : null}
                </div>
              ) : (
                <p className="mt-3 text-sm text-panel-muted">No sync decisions have been recorded for this scope.</p>
              )}
              {latestPreValidationRejection ? (
                <div className="mt-4 rounded-[1rem] border border-panel-table-wrap bg-[color-mix(in_srgb,var(--dashboard-icon-button-surface)_72%,transparent)] px-3 py-3">
                  <div className="flex items-center justify-between gap-3">
                    <strong className="text-sm text-panel-strong">
                      {latestPreValidationRejection.upload_type || latestPreValidationRejection.rejection_stage}
                    </strong>
                    <StatusBadge tone="danger">PRE-VALIDATION</StatusBadge>
                  </div>
                  <p className="mt-2 text-xs leading-5 text-panel-muted">
                    Latest pre-validation rejection: {latestPreValidationRejection.safe_error_summary}
                  </p>
                  {latestPreValidationRejection.field_paths.length ? (
                    <p className="mt-1 text-xs leading-5 text-panel-subtle">
                      Fields: {latestPreValidationRejection.field_paths.slice(0, 3).join(", ")}
                    </p>
                  ) : null}
                </div>
              ) : null}
            </div>
          </Card>
        </section>

        <section className="space-y-5">
          <Card className="overflow-hidden rounded-[2rem] p-5 sm:p-6">
            <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <h2 className="text-[clamp(1.6rem,1rem+1vw,2.35rem)] font-semibold leading-tight text-panel-strong">
                  CHV Ward Coverage
                </h2>
                <p className="mt-2 text-sm text-panel-muted">
                  Coverage-first Migori ward surface showing where CHV presence is good, low, or missing
                </p>
                {wardMap ? (
                  <p className="mt-2 text-xs text-panel-subtle">
                    Geometry coverage: {wardMap.metadata.geometry_feature_count}/{wardMap.metadata.expected_ward_count} wards.
                    {wardMap.metadata.missing_source_wards.length
                      ? ` Source still lacks ${wardMap.metadata.missing_source_wards.join(", ")}.`
                      : ""}
                  </p>
                ) : null}
                {wardMap?.metadata.geometry_note ? (
                  <p className="mt-2 max-w-2xl text-xs text-[color:var(--warning)]">
                    {wardMap.metadata.geometry_note}
                  </p>
                ) : null}
              </div>

              <div className="flex items-center gap-2">
                <button
                  type="button"
                  className={cn(
                    "inline-flex h-10 items-center justify-center rounded-pill px-4 text-sm font-semibold transition",
                    focusFilter === "ALL"
                      ? "bg-brand text-white shadow-[var(--login-submit-shadow)]"
                      : "border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] text-panel-copy",
                  )}
                  onClick={() => setFocusFilter("ALL")}
                >
                  All Wards
                </button>
                <button
                  type="button"
                  className={cn(
                    "inline-flex h-10 items-center justify-center rounded-pill px-4 text-sm font-semibold transition",
                    focusFilter === "HIGH_RISK"
                      ? "bg-brand text-white shadow-[var(--login-submit-shadow)]"
                      : "border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] text-panel-copy",
                  )}
                  onClick={() => setFocusFilter("HIGH_RISK")}
                >
                  Show high-risk wards
                </button>
              </div>
            </div>

            <div className="relative mt-5 min-h-[39rem] overflow-hidden rounded-[1.75rem] border border-panel-table-wrap bg-[radial-gradient(circle_at_top_left,color-mix(in_srgb,var(--brand)_8%,transparent),transparent_34%),linear-gradient(135deg,color-mix(in_srgb,var(--panel)_94%,var(--background-fade)),var(--panel))] p-4">
              <div className="relative z-10 grid h-full gap-4 lg:grid-cols-[minmax(0,1fr)_22rem] xl:grid-cols-[minmax(0,0.95fr)_24rem]">
                <div className="min-h-[34rem] rounded-[1.5rem] border border-panel-table-wrap bg-[color-mix(in_srgb,var(--panel)_92%,transparent)] p-2.5 shadow-[inset_0_1px_0_color-mix(in_srgb,var(--dashboard-table-line)_40%,transparent)]">
                  {mapFeatures.length ? (
                    <div className="flex h-full flex-col gap-4">
                      <div className="flex flex-wrap items-center gap-3 rounded-[1.25rem] border border-panel-table-wrap bg-[color-mix(in_srgb,var(--dashboard-icon-button-surface)_96%,transparent)] px-4 py-3 text-xs text-panel-copy">
                        <span className="inline-flex items-center gap-2">
                          <span className="size-3 rounded-full border border-[#CBD5E1] bg-[#EEF6F2]" />
                          Good
                        </span>
                        <span className="inline-flex items-center gap-2">
                          <span className="size-3 rounded-full border border-[#CBD5E1] bg-[#FFF4E5]" />
                          Low
                        </span>
                        <span className="inline-flex items-center gap-2">
                          <span className="size-3 rounded-full border border-[#DC2626] bg-[#FEE2E2]" />
                          Gap
                        </span>
                        <span className="inline-flex items-center gap-2">
                          <span className="size-3 rounded-full border border-[#94A3B8] bg-[#F1F5F9]" />
                          No data
                        </span>
                      </div>

                      <div className="min-h-[29rem] flex-1">
                        <MigoriWardMap
                          features={mapFeatures}
                          selectedWardCode={selectedMapWard?.properties.ward_code ?? null}
                          focusHighRisk={focusFilter === "HIGH_RISK"}
                          onSelectWard={(feature) =>
                            feature.properties.backend_ward_id
                              ? setSelectedWard(`id:${feature.properties.backend_ward_id}`)
                              : undefined
                          }
                        />
                      </div>
                    </div>
                  ) : (
                    <div className="flex h-full items-center justify-center rounded-[1.25rem] border border-dashed border-panel-table-wrap px-6 text-center text-sm text-panel-muted">
                      Ward geometry is not available for this scope yet.
                    </div>
                  )}
                </div>

                <Card className={cn("rounded-[1.5rem] border px-4 py-4 shadow-none", selectedWardPanelClassName)}>
                  <span className="text-xs font-semibold uppercase tracking-[0.18em] text-panel-subtle">Selected ward</span>
                  {selectedMapWard ? (
                    <div className="mt-4 space-y-4">
                      <div>
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <h3 className="text-lg font-semibold text-panel-strong">{selectedMapWard.properties.name}</h3>
                            <p className="mt-1 text-sm text-panel-muted">
                              {selectedWardLiveRequest
                                ? getCoverageRequestStatusLabel(selectedWardLiveRequest.status)
                                : selectedWardRiskLabel}
                            </p>
                          </div>
                          {selectedWardCoverage ? (
                            <StatusBadge tone={selectedWardCoverage.tone}>{selectedWardCoverage.label}</StatusBadge>
                          ) : null}
                        </div>
                        <p className="mt-3 text-sm text-panel-copy">
                          {selectedWardLiveRequest
                            ? getCoverageRequestStatusMessage(selectedWardLiveRequest)
                            : selectedWardCoverage?.reason ??
                              "Select a ward to review CHV coverage relative to its recorded risk."}
                        </p>
                      </div>

                      <div className="flex flex-col gap-3 rounded-[1.25rem] border border-panel-table-wrap bg-[color-mix(in_srgb,var(--dashboard-icon-button-surface)_76%,transparent)] p-3">
                        <span className="text-[11px] font-semibold uppercase tracking-[0.18em] text-panel-subtle">
                          Recommended action
                        </span>
                        <strong className="text-base text-panel-strong">
                          {selectedWardPrimaryActionLabel}
                        </strong>
                        <p className="text-xs text-panel-muted">{selectedWardPrimaryActionDetail}</p>
                        <div className="grid gap-2 sm:grid-cols-2">
                          <button
                            type="button"
                            className={cn(
                              "inline-flex h-10 items-center justify-center rounded-pill px-4 text-sm font-semibold transition",
                              canRequestCoverageFromSelectedWard
                                ? "bg-brand text-white hover:opacity-95"
                                : "border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] text-panel-muted",
                            )}
                            disabled={!canRequestCoverageFromSelectedWard}
                            onClick={() => {
                              if (!canRequestCoverageFromSelectedWard) {
                                return;
                              }

                              setRequestFeedback(null);
                              setIsCoverageRequestModalOpen(true);
                            }}
                          >
                            Request coverage
                          </button>
                          <a
                            href={selectedWardAlertsHref}
                            className="inline-flex h-10 items-center justify-center rounded-pill border border-panel-table-wrap px-4 text-sm font-semibold text-panel-copy transition hover:border-[var(--dashboard-icon-button-border)] hover:text-panel-strong"
                          >
                            View related alerts
                          </a>
                          {selectedWardLiveRequest ? (
                            <button
                              type="button"
                              className="inline-flex h-10 items-center justify-center rounded-pill border border-panel-table-wrap px-4 text-sm font-semibold text-panel-copy transition hover:border-[var(--dashboard-icon-button-border)] hover:text-panel-strong"
                              onClick={() => {
                                setRequestFeedback(null);
                                setSelectedCoverageRequestId(selectedWardLiveRequest.public_id);
                              }}
                            >
                              View request
                            </button>
                          ) : null}
                        </div>
                        <div className="space-y-1 text-[11px] text-panel-muted">
                          <p>
                            {canRequestCoverageFromSelectedWard
                              ? "Request coverage is available because this ward currently shows a visible coverage gap and no live request."
                              : selectedWardLiveRequest
                                ? "Request coverage stays locked while a live request already exists for this ward."
                                : "Request coverage stays locked until this ward meets the visible gap threshold."}
                          </p>
                        </div>
                        <div className="flex flex-wrap gap-2">
                          {selectedMapWard.properties.backend_ward_id ? (
                            <a
                              href={`/wards/${selectedMapWard.properties.backend_ward_id}`}
                              className={cn(
                                "inline-flex h-10 items-center justify-center whitespace-nowrap rounded-pill px-3 text-xs font-semibold transition sm:px-4",
                                selectedWardLiveRequest || selectedWardCoverage?.label === "Gap"
                                  ? "border border-panel-table-wrap text-panel-copy hover:border-[var(--dashboard-icon-button-border)] hover:text-panel-strong"
                                  : "bg-brand text-white hover:opacity-95",
                              )}
                            >
                              Open Ward Detail
                            </a>
                          ) : null}
                          <a
                            href="#chv-registry"
                            className="inline-flex h-10 items-center justify-center whitespace-nowrap rounded-pill border border-panel-table-wrap px-3 text-xs font-semibold text-panel-copy transition hover:border-[var(--dashboard-icon-button-border)] hover:text-panel-strong sm:px-4"
                          >
                            Review visible CHVs
                          </a>
                        </div>
                      </div>

                      <div className="rounded-[1.25rem] border border-panel-table-wrap bg-[color-mix(in_srgb,var(--dashboard-icon-button-surface)_76%,transparent)] p-3">
                        <span className="text-[11px] font-semibold uppercase tracking-[0.18em] text-panel-subtle">
                          Coverage status
                        </span>
                        <div className="mt-2 flex items-center justify-between gap-3">
                          <strong className="text-base text-panel-strong">
                            {selectedMapWard.properties.active_chv_count}/{selectedMapWard.properties.chv_count} active CHVs
                          </strong>
                          {selectedWardCoverage ? (
                            <StatusBadge tone={selectedWardCoverage.tone}>{selectedWardCoverage.label}</StatusBadge>
                          ) : null}
                        </div>
                        <p className="mt-2 text-xs text-panel-muted">
                          {selectedWardLiveRequest
                            ? `${selectedWardWorkflowSummary?.liveRequestCount ?? 0} live request${selectedWardWorkflowSummary?.liveRequestCount === 1 ? "" : "s"} in this ward.`
                            : `Action recommended: ${selectedWardCoverage?.action ?? "Review ward coverage"}`}
                        </p>
                      </div>

                      <div className="grid gap-3 text-sm text-panel-copy">
                        <div className="flex items-center justify-between gap-3">
                          <span>Recorded risk</span>
                          {selectedMapWard.properties.risk_level ? (
                            <StatusBadge tone={riskTone(resolveRiskZone(selectedMapWard.properties.risk_level))}>
                              {toRiskZoneLabel(resolveRiskZone(selectedMapWard.properties.risk_level))}
                            </StatusBadge>
                          ) : (
                            <StatusBadge tone="default">No backend risk</StatusBadge>
                          )}
                        </div>
                        <div className="flex items-center justify-between gap-3">
                          <span>Active CHVs / total CHVs</span>
                          <strong className="text-panel-strong">
                            {selectedMapWard.properties.active_chv_count}/{selectedMapWard.properties.chv_count}
                          </strong>
                        </div>
                        <div className="flex items-center justify-between gap-3">
                          <span>Predicted cases</span>
                          <strong className="text-panel-strong">{selectedMapWard.properties.predicted_cases}</strong>
                        </div>
                        <div className="flex items-center justify-between gap-3">
                          <span>Open alert records</span>
                          <strong className="text-panel-strong">{filteredWardAlertCount || selectedMapWard.properties.alert_count}</strong>
                        </div>
                        <div className="flex items-center justify-between gap-3">
                          <span>Live coverage requests</span>
                          <strong className="text-panel-strong">{selectedWardWorkflowSummary?.liveRequestCount ?? 0}</strong>
                        </div>
                        <div className="flex items-center justify-between gap-3">
                          <span>Active assignments</span>
                          <strong className="text-panel-strong">{selectedWardWorkflowSummary?.activeAssignmentCount ?? 0}</strong>
                        </div>
                        <div className="flex items-center justify-between gap-3">
                          <span>Active facilities</span>
                          <strong className="text-panel-strong">{selectedMapWard.properties.facility_count}</strong>
                        </div>
                        <div className="flex items-center justify-between gap-3">
                          <span>Last CHV activity</span>
                          <strong className="text-right text-panel-strong">
                            {selectedWardLatestActivity ? formatRelativeTimestamp(selectedWardLatestActivity) : "No recent activity"}
                          </strong>
                        </div>
                        <div className="flex items-center justify-between gap-3">
                          <span>Sync freshness</span>
                          <StatusBadge tone={selectedWardLatestSync ? (selectedWardSyncFreshness.isStale ? "warning" : "success") : "default"}>
                            {selectedWardLatestSync ? selectedWardSyncFreshness.label : "No sync recorded"}
                          </StatusBadge>
                        </div>
                        <div className="flex items-center justify-between gap-3">
                          <span>Ward code</span>
                          <strong className="text-panel-strong">{selectedMapWard.properties.ward_code}</strong>
                        </div>
                      </div>
                    </div>
                  ) : (
                    <p className="mt-4 text-sm text-panel-muted">
                      Select a ward on the map to inspect its visible backend-backed counts.
                    </p>
                  )}
                </Card>
              </div>
            </div>
          </Card>

          <div className="grid gap-5 xl:grid-cols-2">
            <Card className="rounded-[2rem] px-5 py-5">
              <h2 className="text-2xl font-semibold text-panel-strong">Operational Insights</h2>
              <p className="mt-3 text-sm text-panel-muted">
                Coverage gaps, sync delays, and field activity below are derived from visible records and meant to guide follow-up.
              </p>

              <div className="mt-5 space-y-3">
                {operationalInsights.map((insight) => (
                  <div
                    key={insight}
                    className="flex items-start gap-3 rounded-[1.5rem] border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] px-4 py-4"
                  >
                    <span className="mt-2 inline-flex size-2 rounded-full bg-brand" aria-hidden="true" />
                    <p className="text-sm leading-6 text-panel-copy">{insight}</p>
                  </div>
                ))}
              </div>
            </Card>

            <Card
              className={cn(
                "rounded-[2rem] px-5 py-5",
                coverageSummary.gap
                  ? "border-[color:var(--danger)]/18 bg-[color-mix(in_srgb,var(--danger)_5%,var(--panel))]"
                  : coverageSummary.low
                    ? "border-[color:var(--warning)]/25 bg-[color-mix(in_srgb,var(--warning)_8%,var(--panel))]"
                    : "border-[color:var(--success)]/25 bg-[color-mix(in_srgb,var(--success)_6%,var(--panel))]",
              )}
            >
              <div className="flex items-center gap-3">
                <span
                  className={cn(
                    "inline-flex size-10 items-center justify-center rounded-full",
                    coverageSummary.gap
                      ? "bg-[color-mix(in_srgb,var(--danger)_16%,white)] text-[color:var(--danger)] dark:bg-[color-mix(in_srgb,var(--danger)_20%,transparent)]"
                      : coverageSummary.low
                        ? "bg-[color-mix(in_srgb,var(--warning)_18%,white)] text-[color:var(--warning)] dark:bg-[color-mix(in_srgb,var(--warning)_20%,transparent)]"
                        : "bg-[color-mix(in_srgb,var(--success)_18%,white)] text-[color:var(--success)] dark:bg-[color-mix(in_srgb,var(--success)_20%,transparent)]",
                  )}
                >
                  <ShieldAlert className="size-4" aria-hidden="true" />
                </span>
                <h3 className="text-xl font-semibold text-panel-strong">Coverage Summary</h3>
              </div>
              <div className="mt-4 grid gap-3 sm:grid-cols-2">
                <div className="rounded-[1.25rem] border border-panel-table-wrap bg-[color-mix(in_srgb,var(--dashboard-icon-button-surface)_74%,transparent)] px-4 py-3">
                  <span className="text-[11px] font-semibold uppercase tracking-[0.16em] text-panel-subtle">Current view</span>
                  <p className="mt-2 text-xs leading-5 text-panel-muted">
                    Gap = 0 active CHVs, or only 1 active CHV in a high-risk ward. Low = below the visible risk threshold.
                  </p>
                  <div className="mt-3 space-y-2 text-sm text-panel-copy">
                    <div className="flex items-center justify-between gap-3">
                      <span>Gap wards (0 active CHVs)</span>
                      <strong className="text-[color:var(--danger)]">{coverageSummary.gap}</strong>
                    </div>
                    <div className="flex items-center justify-between gap-3">
                      <span>Below visible threshold</span>
                      <strong className="text-[color:var(--warning)]">{coverageSummary.low}</strong>
                    </div>
                    <div className="flex items-center justify-between gap-3">
                      <span>Meets visible threshold</span>
                      <strong className="text-[color:var(--success)]">{coverageSummary.good}</strong>
                    </div>
                    <div className="flex items-center justify-between gap-3">
                      <span>No data</span>
                      <strong className="text-panel-muted">{coverageSummary.noData}</strong>
                    </div>
                  </div>
                </div>

                <div className="rounded-[1.25rem] border border-panel-table-wrap bg-[color-mix(in_srgb,var(--dashboard-icon-button-surface)_74%,transparent)] px-4 py-3">
                  <span className="text-[11px] font-semibold uppercase tracking-[0.16em] text-panel-subtle">Top priority</span>
                  {coverageSummary.priorities.length ? (
                    <div className="mt-3 space-y-3">
                      {coverageSummary.priorities.map((item) => (
                        <div key={item.name} className="flex items-start justify-between gap-3 text-sm">
                          <div>
                            <strong className="block text-panel-strong">{item.name}</strong>
                            <span className="text-panel-muted">{item.activeChvs} active CHVs</span>
                          </div>
                          <StatusBadge tone={item.tone === "gap" ? "danger" : "warning"}>
                            {item.tone === "gap" ? "Gap" : "Low"}
                          </StatusBadge>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="mt-3 text-sm text-panel-muted">No wards currently stand out for immediate CHV coverage follow-up.</p>
                  )}
                </div>
              </div>
              <p className="mt-5 text-sm text-panel-muted">
                Use the selected ward panel and CHV registry below to review the specific volunteers linked to the highest-priority gaps.
              </p>
            </Card>
          </div>
        </section>

        <Card id="chv-registry" className="rounded-[2rem] px-5 py-5 sm:px-6">
          <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
            <div>
              <h2 className="text-[clamp(1.6rem,1rem+1vw,2.3rem)] font-semibold leading-tight text-panel-strong">
                CHV Personnel Registry
              </h2>
              <p className="mt-2 text-sm text-panel-muted">Recorded CHV identity, sync, alert, and ward-linked status fields</p>
              {selectedWard !== "ALL" && selectedWardName ? (
                <p className="mt-2 text-xs font-medium text-brand">
                  Registry filtered to {selectedWardName} from the ward coverage view.
                </p>
              ) : null}
            </div>

            <div className="flex min-w-0 flex-1 flex-col gap-4 xl:max-w-3xl xl:flex-row xl:flex-wrap xl:justify-end">
              <InputShell
                className="min-w-0 flex-[1.2]"
                icon={<Search className="size-4" aria-hidden="true" />}
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search by name..."
                aria-label="Search by name"
              />

              <label className="flex min-w-[12rem] flex-col">
                <span className="relative flex h-11 items-center rounded-pill border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] px-4 shadow-sm">
                  <select
                    value={selectedWard}
                    onChange={(event) => setSelectedWard(event.target.value as SelectedWardFilter)}
                    aria-label="Ward filter"
                    className="h-full w-full appearance-none bg-transparent pr-8 text-sm text-panel-strong outline-none"
                  >
                    {wardsForFilter.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </span>
              </label>

              <Button variant="secondary" size="icon" className="size-11" aria-label="More filters">
                <Filter className="size-4" aria-hidden="true" />
              </Button>
            </div>
          </div>

          <div className="mt-5 flex flex-wrap gap-2">
            {[
              { value: "ALL", label: "All" },
              { value: "ACTIVE", label: "Active" },
              { value: "IDLE", label: "Idle" },
              { value: "OFFLINE", label: "Offline" },
              { value: "HIGH_RISK", label: "High-risk wards" },
            ].map((filterOption) => (
              <button
                key={filterOption.value}
                type="button"
                className={cn(
                  "inline-flex h-10 items-center justify-center rounded-pill border px-4 text-sm font-semibold transition",
                  quickFilter === filterOption.value
                    ? "border-brand bg-brand text-white shadow-[var(--login-submit-shadow)]"
                    : "border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] text-panel-copy hover:border-[var(--dashboard-icon-button-border)] hover:text-panel-strong",
                )}
                onClick={() => setQuickFilter(filterOption.value as QuickFilter)}
              >
                {filterOption.label}
              </button>
            ))}
          </div>

          <div className="mt-6 overflow-hidden rounded-[1.5rem] border border-panel-table-wrap">
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-panel-table-wrap text-sm">
                <thead className="bg-[color-mix(in_srgb,var(--dashboard-table-line)_30%,transparent)]">
                  <tr className="text-left">
              {[
                  "Volunteer name",
                  "Ward",
                  "Status",
                  "Ward alerts (Total/Delivered)",
                  "Sync health",
                  "Last sync",
                  "Ward risk",
                      "Record",
                    ].map((label) => (
                      <th
                        key={label}
                        className="px-5 py-4 text-[0.72rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle"
                      >
                        {label}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-panel-table-wrap bg-panel">
                  {isLoading ? (
                    Array.from({ length: 3 }).map((_, index) => (
                      <tr key={`skeleton-${index}`}>
                        <td colSpan={8} className="px-5 py-5">
                          <div className="h-6 w-full animate-pulse rounded-full bg-[color-mix(in_srgb,var(--dashboard-table-line)_55%,transparent)]" />
                        </td>
                      </tr>
                    ))
                  ) : pagedRows.length ? (
                    pagedRows.map((row) => (
                      <tr
                        key={row.id}
                        onClick={() => setSelectedChvId(row.id)}
                        className={cn(
                          "cursor-pointer transition hover:bg-[color-mix(in_srgb,var(--dashboard-nav-hover)_40%,transparent)]",
                          selectedWardId === row.wardId &&
                            "bg-[color-mix(in_srgb,var(--brand)_6%,transparent)]",
                        )}
                      >
                        <td className="px-5 py-4 align-top">
                          <div className="flex items-center gap-3">
                            <span className="inline-flex size-11 items-center justify-center rounded-full bg-[color-mix(in_srgb,var(--brand)_12%,white)] text-sm font-semibold text-brand dark:bg-[color-mix(in_srgb,var(--brand)_18%,transparent)]">
                              {row.initials}
                            </span>
                            <div>
                              <strong className="block text-base text-panel-strong">{row.name}</strong>
                              <small className="text-sm text-panel-muted">{row.rosterId}</small>
                            </div>
                          </div>
                        </td>
                        <td className="px-5 py-4 align-top text-panel-copy">{row.wardName}</td>
                        <td className="px-5 py-4 align-top">
                          <div className="space-y-2">
                            <StatusBadge tone={statusTone(row.status)} className="tracking-[0.12em]">
                              {toTitleStatus(row.status)}
                            </StatusBadge>
                            {row.status === "OFFLINE" ? (
                              <p className="text-xs font-medium text-[color:var(--danger)]">Needs follow-up</p>
                            ) : null}
                          </div>
                        </td>
                        <td className="px-5 py-4 align-top text-panel-copy">
                          {row.alertsRaised} / {row.alertsAcknowledged}
                        </td>
                        <td className="px-5 py-4 align-top">
                          <StatusBadge tone={syncTone(row.syncHealth)} className="tracking-[0.12em]">
                            {toSyncHealthLabel(row.syncHealth)}
                          </StatusBadge>
                        </td>
                        <td className="px-5 py-4 align-top">
                          <div className="space-y-2 text-panel-copy">
                            <div>{row.lastSync}</div>
                            {row.lastSync === "No sync recorded" ? (
                              <p className="text-xs font-medium text-[color:var(--warning)]">No sync recorded</p>
                            ) : null}
                          </div>
                        </td>
                        <td className="px-5 py-4 align-top">
                          <StatusBadge tone={riskTone(row.riskZone)} className="tracking-[0.12em]">
                            {toRiskZoneLabel(row.riskZone)}
                          </StatusBadge>
                        </td>
                        <td className="px-5 py-4 align-top">
                          <div className="flex items-center gap-2" onClick={(event) => event.stopPropagation()}>
                            <Button variant="ghost" className="h-9 rounded-pill px-3 text-sm" onClick={() => setSelectedChvId(row.id)}>
                              Open
                            </Button>
                            <a
                              href={`/wards/${row.wardId}`}
                              className="inline-flex h-9 items-center justify-center rounded-pill border border-panel-table-wrap px-3 text-sm font-semibold text-panel-copy transition hover:border-[var(--dashboard-icon-button-border)] hover:text-panel-strong"
                            >
                              Ward
                            </a>
                          </div>
                        </td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={8} className="px-5 py-10 text-center text-sm text-panel-muted">
                        No CHVs match the selected filters.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          <div className="mt-5 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <span className="text-sm text-panel-muted">
              Showing {pagedRows.length} of {registryRows.length || 0} volunteers
            </span>
            {totalPages > 1 ? (
              <div className="flex items-center gap-2">
                <Button
                  variant="secondary"
                  size="icon"
                  className="size-10"
                  onClick={() => setCurrentPage((page) => Math.max(1, page - 1))}
                  disabled={clampedPage === 1}
                  aria-label="Previous page"
                >
                  <ChevronLeft className="size-4" aria-hidden="true" />
                </Button>
                <Button
                  variant="secondary"
                  size="icon"
                  className="size-10"
                  onClick={() => setCurrentPage((page) => Math.min(totalPages, page + 1))}
                  disabled={clampedPage === totalPages}
                  aria-label="Next page"
                >
                  <ChevronRight className="size-4" aria-hidden="true" />
                </Button>
              </div>
            ) : null}
          </div>
        </Card>

        {isCoverageRequestModalOpen && selectedMapWard ? (
          <>
            <button
              type="button"
              className="fixed inset-0 z-40 bg-slate-950/50 backdrop-blur-[1px]"
              aria-label="Close coverage request modal"
              onClick={() => setIsCoverageRequestModalOpen(false)}
            />
            <aside className="fixed inset-y-0 right-0 z-50 flex w-full max-w-[30rem] flex-col border-l border-panel-border bg-panel shadow-2xl">
              <div className="flex items-start justify-between gap-4 border-b border-panel-table-wrap px-5 py-5 sm:px-6">
                <div>
                  <span className="text-xs font-semibold uppercase tracking-[0.18em] text-panel-subtle">Request coverage</span>
                  <h2 className="mt-2 text-2xl font-semibold text-panel-strong">{selectedMapWard.properties.name}</h2>
                  <p className="mt-1 text-sm text-panel-muted">Create a real CHV coverage request for this ward.</p>
                </div>
                <Button
                  variant="ghost"
                  size="icon"
                  className="size-10 shrink-0"
                  onClick={() => setIsCoverageRequestModalOpen(false)}
                  aria-label="Close coverage request modal"
                >
                  <X className="size-4" aria-hidden="true" />
                </Button>
              </div>

              <div className="flex-1 space-y-5 overflow-y-auto px-5 py-5 sm:px-6">
                {createCoverageRequestMutation.error instanceof Error ? (
                  <StatusBanner tone="danger">{createCoverageRequestMutation.error.message}</StatusBanner>
                ) : null}
                <Card className="rounded-2xl px-4 py-4 shadow-none">
                  <h3 className="text-sm font-semibold uppercase tracking-[0.16em] text-panel-subtle">Request details</h3>
                  <div className="mt-4 space-y-4 text-sm text-panel-copy">
                    <div>
                      <span className="block text-xs font-semibold uppercase tracking-[0.16em] text-panel-subtle">Ward</span>
                      <strong className="mt-1 block text-panel-strong">{selectedMapWard.properties.name}</strong>
                    </div>
                    <label className="block">
                      <span className="block text-xs font-semibold uppercase tracking-[0.16em] text-panel-subtle">Priority</span>
                      <select
                        value={requestPriority}
                        onChange={(event) => setRequestPriority(event.target.value as ChvCoverageRequestPriority)}
                        className="mt-2 h-11 w-full rounded-2xl border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] px-4 text-sm text-panel-strong outline-none"
                      >
                        <option value="LOW">Low</option>
                        <option value="MEDIUM">Medium</option>
                        <option value="HIGH">High</option>
                      </select>
                    </label>
                    <label className="block">
                      <span className="block text-xs font-semibold uppercase tracking-[0.16em] text-panel-subtle">Requested CHVs</span>
                      <input
                        type="number"
                        min={1}
                        max={10}
                        value={requestCount}
                        onChange={(event) => setRequestCount(Number(event.target.value) || 1)}
                        className="mt-2 h-11 w-full rounded-2xl border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] px-4 text-sm text-panel-strong outline-none"
                      />
                    </label>
                    <label className="block">
                      <span className="block text-xs font-semibold uppercase tracking-[0.16em] text-panel-subtle">Reason</span>
                      <textarea
                        value={requestReason}
                        onChange={(event) => setRequestReason(event.target.value)}
                        rows={4}
                        className="mt-2 w-full rounded-2xl border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] px-4 py-3 text-sm text-panel-strong outline-none"
                      />
                    </label>
                    <label className="block">
                      <span className="block text-xs font-semibold uppercase tracking-[0.16em] text-panel-subtle">Notes</span>
                      <textarea
                        value={requestNotes}
                        onChange={(event) => setRequestNotes(event.target.value)}
                        rows={3}
                        className="mt-2 w-full rounded-2xl border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] px-4 py-3 text-sm text-panel-strong outline-none"
                      />
                    </label>
                  </div>
                </Card>
              </div>

              <div className="flex flex-col gap-3 border-t border-panel-table-wrap px-5 py-5 sm:px-6">
                <Button
                  onClick={async () => {
                    if (!selectedMapWard.properties.backend_ward_id) {
                      return;
                    }

                    try {
                      const result = await createCoverageRequestMutation.mutateAsync({
                        ward_id: selectedMapWard.properties.backend_ward_id,
                        priority: requestPriority,
                        reason: requestReason.trim(),
                        requested_chv_count: requestCount,
                        notes: requestNotes.trim(),
                      });
                      setRequestFeedback(`Coverage request created for ${selectedMapWard.properties.name}.`);
                      setIsCoverageRequestModalOpen(false);
                      setSelectedCoverageRequestId(result.public_id);
                    } catch {
                      // The mutation hook already exposes the backend error for the modal banner.
                    }
                  }}
                  disabled={createCoverageRequestMutation.isPending || !requestReason.trim()}
                >
                  {createCoverageRequestMutation.isPending ? "Creating request..." : "Create coverage request"}
                </Button>
                <Button variant="secondary" onClick={() => setIsCoverageRequestModalOpen(false)}>
                  Cancel
                </Button>
              </div>
            </aside>
          </>
        ) : null}

        {selectedCoverageRequestId ? (
          <>
            <button
              type="button"
              className="fixed inset-0 z-40 bg-slate-950/50 backdrop-blur-[1px]"
              aria-label="Close coverage request drawer"
              onClick={() => setSelectedCoverageRequestId(null)}
            />
            <aside className="fixed inset-y-0 right-0 z-50 flex w-full max-w-[30rem] flex-col border-l border-panel-border bg-panel shadow-2xl">
              <div className="flex items-start justify-between gap-4 border-b border-panel-table-wrap px-5 py-5 sm:px-6">
                <div>
                  <span className="text-xs font-semibold uppercase tracking-[0.18em] text-panel-subtle">Coverage request</span>
                  <h2 className="mt-2 text-2xl font-semibold text-panel-strong">
                    {selectedCoverageRequestDetail?.ward_name ?? "Coverage request"}
                  </h2>
                  <p className="mt-1 text-sm text-panel-muted">
                    {selectedCoverageRequestDetail ? getCoverageRequestStatusLabel(selectedCoverageRequestDetail.status) : "Loading request details"}
                  </p>
                </div>
                <Button
                  variant="ghost"
                  size="icon"
                  className="size-10 shrink-0"
                  onClick={() => setSelectedCoverageRequestId(null)}
                  aria-label="Close coverage request drawer"
                >
                  <X className="size-4" aria-hidden="true" />
                </Button>
              </div>

              <div className="flex-1 space-y-5 overflow-y-auto px-5 py-5 sm:px-6">
                {selectedCoverageRequestDetailQuery.error instanceof Error ? (
                  <StatusBanner tone="danger">{selectedCoverageRequestDetailQuery.error.message}</StatusBanner>
                ) : null}
                {assignCoverageRequestMutation.error instanceof Error ? (
                  <StatusBanner tone="danger">{assignCoverageRequestMutation.error.message}</StatusBanner>
                ) : null}
                {selectedCoverageRequestDetailQuery.isPending && !selectedCoverageRequestDetail ? (
                  <Card className="rounded-2xl px-4 py-6 shadow-none">
                    <p className="text-sm text-panel-muted">Loading coverage request details...</p>
                  </Card>
                ) : null}
                {selectedCoverageRequestDetail ? (
                  <>
                <Card className="rounded-2xl px-4 py-4 shadow-none">
                  <h3 className="text-sm font-semibold uppercase tracking-[0.16em] text-panel-subtle">Request summary</h3>
                  <div className="mt-4 space-y-3 text-sm text-panel-copy">
                    <div className="flex items-center justify-between gap-3">
                      <span>Status</span>
                      <strong className="text-panel-strong">{selectedCoverageRequestDetail.status}</strong>
                    </div>
                    <div className="flex items-center justify-between gap-3">
                      <span>Priority</span>
                      <strong className="text-panel-strong">{selectedCoverageRequestDetail.priority}</strong>
                    </div>
                    <div className="flex items-center justify-between gap-3">
                      <span>Source</span>
                      <strong className="text-panel-strong">
                        {hasStoredAlertLinkage(selectedCoverageRequestDetail) ? "Alert-driven" : "Manual"}
                      </strong>
                    </div>
                    <div className="flex items-center justify-between gap-3">
                      <span>Requested CHVs</span>
                      <strong className="text-panel-strong">{selectedCoverageRequestDetail.requested_chv_count}</strong>
                    </div>
                    <div className="flex items-center justify-between gap-3">
                      <span>Requested by</span>
                      <strong className="text-panel-strong">{selectedCoverageRequestDetail.requested_by_username ?? "Unknown"}</strong>
                    </div>
                    <div className="flex items-center justify-between gap-3">
                      <span>Created</span>
                      <strong className="text-panel-strong">{formatRelativeTimestamp(selectedCoverageRequestDetail.created_at)}</strong>
                    </div>
                  </div>
                </Card>

                <Card className="rounded-2xl px-4 py-4 shadow-none">
                  <h3 className="text-sm font-semibold uppercase tracking-[0.16em] text-panel-subtle">Request source</h3>
                  <p className="mt-3 text-sm leading-6 text-panel-copy">
                    {getCoverageRequestSourceDescription(selectedCoverageRequestDetail)}
                  </p>
                  {selectedCoverageRequestDetail.linked_alerts_summary.length ? (
                    <div className="mt-4 space-y-3">
                      {selectedCoverageRequestDetail.linked_alerts_summary.map((alertSummary) => (
                        <div key={alertSummary.alert_public_id} className="rounded-2xl border border-panel-table-wrap px-4 py-3">
                          <div className="flex items-center justify-between gap-3">
                            <strong className="text-sm text-panel-strong">Alert {alertSummary.alert_public_id}</strong>
                            <StatusBadge tone={alertSummary.status === "DELIVERED" ? "success" : alertSummary.status === "FAILED" ? "warning" : "info"}>
                              {alertSummary.status}
                            </StatusBadge>
                          </div>
                          <p className="mt-2 text-sm text-panel-copy">
                            {alertSummary.ward_name ?? selectedCoverageRequestDetail.ward_name} · {alertSummary.channel}
                          </p>
                        </div>
                      ))}
                    </div>
                  ) : null}
                </Card>

                <Card className="rounded-2xl px-4 py-4 shadow-none">
                  <h3 className="text-sm font-semibold uppercase tracking-[0.16em] text-panel-subtle">Reason</h3>
                  <p className="mt-3 text-sm leading-6 text-panel-copy">{selectedCoverageRequestDetail.reason}</p>
                  {selectedCoverageRequestDetail.notes ? (
                    <p className="mt-3 text-sm leading-6 text-panel-muted">{selectedCoverageRequestDetail.notes}</p>
                  ) : null}
                </Card>

                {selectedCoverageRequestDetail.status === "APPROVED" && hasFreshSelectedCoverageRequestDetail ? (
                  <Card className="rounded-2xl px-4 py-4 shadow-none">
                    <h3 className="text-sm font-semibold uppercase tracking-[0.16em] text-panel-subtle">Assign CHV</h3>
                    <p className="mt-3 text-sm leading-6 text-panel-copy">
                      Assignment is only available inside request detail after approval. Select a real active CHV linked to this ward.
                    </p>
                    {assignableWardChvs.length ? (
                      <div className="mt-4 space-y-4">
                        <select
                          value={assignmentChvId ?? ""}
                          onChange={(event) => setAssignmentChvId(Number(event.target.value) || null)}
                          className="h-11 w-full rounded-2xl border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] px-4 text-sm text-panel-strong outline-none"
                        >
                          {assignableWardChvs.map((chv) => (
                            <option key={chv.id} value={chv.id}>
                              {chv.name} · {chv.phone_number}
                            </option>
                          ))}
                        </select>
                        <textarea
                          value={assignmentNotes}
                          onChange={(event) => setAssignmentNotes(event.target.value)}
                          rows={3}
                          placeholder="Optional assignment notes"
                          className="w-full rounded-2xl border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] px-4 py-3 text-sm text-panel-strong outline-none"
                        />
                        <Button
                          disabled={!assignmentChvId || assignCoverageRequestMutation.isPending}
                          onClick={async () => {
                            if (!assignmentChvId || !selectedCoverageRequestDetail) {
                              return;
                            }

                            try {
                              await assignCoverageRequestMutation.mutateAsync({
                                publicId: selectedCoverageRequestDetail.public_id,
                                payload: {
                                  chv_id: assignmentChvId,
                                  notes: assignmentNotes.trim(),
                                },
                              });
                              setRequestFeedback(`CHV assigned for ${selectedCoverageRequestDetail.ward_name}.`);
                            } catch {
                              // Hook exposes backend error banner.
                            }
                          }}
                        >
                          {assignCoverageRequestMutation.isPending ? "Assigning CHV..." : "Assign CHV"}
                        </Button>
                      </div>
                    ) : (
                      <StatusBanner tone="warning" className="mt-4">
                        No active CHVs are currently available in this ward for direct assignment from this surface.
                      </StatusBanner>
                    )}
                  </Card>
                ) : null}

                <Card className="rounded-2xl px-4 py-4 shadow-none">
                  <h3 className="text-sm font-semibold uppercase tracking-[0.16em] text-panel-subtle">Timeline</h3>
                  <div className="mt-4 space-y-3">
                    {selectedCoverageRequestDetail.events.length ? (
                      selectedCoverageRequestDetail.events.map((event) => (
                        <div key={event.public_id} className="rounded-2xl border border-panel-table-wrap px-4 py-3 text-sm">
                          <div className="flex items-center justify-between gap-3">
                            <strong className="text-panel-strong">{event.action.replaceAll("_", " ")}</strong>
                            <span className="text-panel-muted">{formatRelativeTimestamp(event.created_at)}</span>
                          </div>
                          <p className="mt-2 text-panel-copy">{event.detail}</p>
                        </div>
                      ))
                    ) : (
                      <p className="text-sm text-panel-muted">No workflow events are recorded for this request yet.</p>
                    )}
                  </div>
                </Card>
                <div className="flex flex-wrap gap-3">
                  <a
                    href={`/chvs/requests/${selectedCoverageRequestDetail.public_id}`}
                    className="inline-flex h-10 items-center justify-center rounded-pill bg-brand px-4 text-sm font-semibold text-white transition hover:opacity-95"
                  >
                    Open full request
                  </a>
                </div>
                  </>
                ) : null}
              </div>
            </aside>
          </>
        ) : null}

        {selectedChv ? (
          <>
            <button
              type="button"
              className="fixed inset-0 z-40 bg-slate-950/50 backdrop-blur-[1px]"
              aria-label="Close CHV detail drawer"
              onClick={() => setSelectedChvId(null)}
            />
            <aside className="fixed inset-y-0 right-0 z-50 flex w-full max-w-[30rem] flex-col border-l border-panel-border bg-panel shadow-2xl">
              <div className="flex items-start justify-between gap-4 border-b border-panel-table-wrap px-5 py-5 sm:px-6">
                <div>
                  <span className="text-xs font-semibold uppercase tracking-[0.18em] text-panel-subtle">CHV detail</span>
                  <h2 className="mt-2 text-2xl font-semibold text-panel-strong">{selectedChv.name}</h2>
                  <p className="mt-1 text-sm text-panel-muted">
                    {selectedChv.rosterId} · {selectedChv.wardName}
                  </p>
                </div>
                <Button
                  variant="ghost"
                  size="icon"
                  className="size-10 shrink-0"
                  onClick={() => setSelectedChvId(null)}
                  aria-label="Close CHV detail"
                >
                  <X className="size-4" aria-hidden="true" />
                </Button>
              </div>

              <div className="flex-1 space-y-5 overflow-y-auto px-5 py-5 sm:px-6">
                <div className="grid gap-3 sm:grid-cols-2">
                  {[
                    ["Status", toTitleStatus(selectedChv.status)],
                    ["Sync health", toSyncHealthLabel(selectedChv.syncHealth)],
                    ["Ward alerts", `${selectedChv.alertsRaised} total / ${selectedChv.alertsAcknowledged} delivered`],
                    ["Ward risk", toRiskZoneLabel(selectedChv.riskZone)],
                  ].map(([label, value]) => (
                    <Card key={label} className="rounded-2xl px-4 py-4 shadow-none">
                      <span className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-subtle">{label}</span>
                      <strong className="mt-2 block text-base text-panel-strong">{value}</strong>
                    </Card>
                  ))}
                </div>

                <Card className="rounded-2xl px-4 py-4 shadow-none">
                  <h3 className="text-sm font-semibold uppercase tracking-[0.16em] text-panel-subtle">Field profile</h3>
                  <ul className="mt-4 space-y-3 text-sm text-panel-copy">
                    <li className="flex items-center gap-3">
                      <Smartphone className="size-4 text-panel-muted" aria-hidden="true" />
                      {selectedChv.phoneNumber}
                    </li>
                    <li className="flex items-center gap-3">
                      <Activity className="size-4 text-panel-muted" aria-hidden="true" />
                      Language: {selectedChv.language}
                    </li>
                    <li className="flex items-center gap-3">
                      {selectedChv.syncHealth === "OFFLINE" ? (
                        <WifiOff className="size-4 text-panel-muted" aria-hidden="true" />
                      ) : (
                        <Wifi className="size-4 text-panel-muted" aria-hidden="true" />
                      )}
                      Connectivity: {toSyncHealthLabel(selectedChv.syncHealth)}
                    </li>
                    <li className="flex items-center gap-3">
                      <Clock3 className="size-4 text-panel-muted" aria-hidden="true" />
                      Last sync: {selectedChv.lastSync}
                    </li>
                  </ul>
                </Card>

                <Card className="rounded-2xl px-4 py-4 shadow-none">
                  <h3 className="text-sm font-semibold uppercase tracking-[0.16em] text-panel-subtle">Latest activity</h3>
                  <p className="mt-3 text-sm leading-6 text-panel-copy">
                    {selectedChv.lastProtocolUpdate === "No recent activity"
                      ? "No recent activity recorded for this CHV."
                      : `Last recorded activity ${selectedChv.lastProtocolUpdate}.`}
                  </p>
                  {latestChvMessage ? (
                    <p className="mt-3 text-sm leading-6 text-panel-muted">
                      Latest message status: {latestChvMessage.status.toLowerCase().replace("_", " ")}{" "}
                      {formatRelativeTimestamp(latestChvMessage.created_at)}.
                    </p>
                  ) : null}
                </Card>

              </div>

              <div className="border-t border-panel-table-wrap px-5 py-5 sm:px-6">
                {selectedChv.canMessage || selectedChv.canViewActivity ? (
                  <div className="space-y-3">
                    {selectedChv.canMessage ? (
                      <Button
                        type="button"
                        className="w-full rounded-full"
                        onClick={() => {
                          setMessageFeedback(null);
                          setIsChvMessageModalOpen(true);
                        }}
                      >
                        Message CHV
                      </Button>
                    ) : null}
                    {selectedChv.messageMode === "QUEUE_ONLY" ? (
                      <p className="text-sm leading-6 text-panel-muted">Messages from this screen are queued for follow-up rather than sent live.</p>
                    ) : selectedChv.canMessage ? (
                      <p className="text-sm leading-6 text-panel-muted">
                        {getChvMessageCapabilityLabel(selectedChv.messageMode, selectedChv.messageDeliveryKind)}
                      </p>
                    ) : null}
                  </div>
                ) : (
                  <p className="text-sm leading-6 text-panel-muted">
                    This screen currently supports CHV profile and sync review only.
                  </p>
                )}
              </div>
            </aside>
            {isChvMessageModalOpen ? (
              <>
                <button
                  type="button"
                  className="fixed inset-0 z-[60] bg-slate-950/60"
                  aria-label="Close CHV messaging modal"
                  onClick={() => setIsChvMessageModalOpen(false)}
                />
                <div className="fixed inset-0 z-[70] flex items-center justify-center p-4">
                  <Card className="w-full max-w-2xl rounded-[2rem] border border-panel-border bg-panel p-6 shadow-2xl">
                    <div className="flex items-start justify-between gap-4">
                      <div>
                        <span className="text-xs font-semibold uppercase tracking-[0.18em] text-panel-subtle">CHV messaging</span>
                        <h3 className="mt-2 text-2xl font-semibold text-panel-strong">Message {selectedChv.name}</h3>
                        <p className="mt-1 text-sm text-panel-muted">
                          {selectedChv.phoneNumber} · {getChvMessageCapabilityLabel(selectedChv.messageMode, selectedChv.messageDeliveryKind)}
                        </p>
                      </div>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="size-10 shrink-0"
                        onClick={() => setIsChvMessageModalOpen(false)}
                        aria-label="Close CHV messaging modal"
                      >
                        <X className="size-4" aria-hidden="true" />
                      </Button>
                    </div>

                    <div className="mt-6 space-y-5">
                      {messageFeedback ? <StatusBanner tone="success">{messageFeedback}</StatusBanner> : null}
                      {createChvMessageMutation.error ? <StatusBanner tone="danger">{createChvMessageMutation.error.message}</StatusBanner> : null}

                      <div>
                        <p className="text-sm font-medium text-panel-strong">Templates</p>
                        <div className="mt-3 flex flex-wrap gap-2">
                          {selectedChvMessageTemplates.map((template) => (
                            <button
                              key={template.label}
                              type="button"
                              onClick={() => {
                                setSelectedMessageTemplateLabel(template.label);
                                setMessageBody(template.body);
                              }}
                              className={cn(
                                "rounded-full border px-3 py-2 text-xs font-semibold transition",
                                selectedMessageTemplateLabel === template.label
                                  ? "border-brand-primary bg-brand-primary/15 text-brand-primary"
                                  : "border-panel-border text-panel-copy hover:border-brand-primary/40 hover:text-panel-strong",
                              )}
                              aria-pressed={selectedMessageTemplateLabel === template.label}
                            >
                              {template.label}
                            </button>
                          ))}
                        </div>
                      </div>

                      <label className="block">
                        <span className="text-sm font-medium text-panel-strong">Message body</span>
                        <textarea
                          value={messageBody}
                          onChange={(event) => {
                            setSelectedMessageTemplateLabel(null);
                            setMessageBody(event.target.value);
                          }}
                          rows={6}
                          className="mt-3 w-full rounded-3xl border border-panel-border bg-panel px-4 py-3 text-sm text-panel-copy outline-none transition focus:border-brand-primary/40"
                          placeholder="Write the message you want to send to this CHV."
                        />
                      </label>

                      <div>
                        <p className="text-sm font-medium text-panel-strong">Recent messages</p>
                        {isChvMessagesPending ? (
                          <p className="mt-3 text-sm leading-6 text-panel-muted">Loading recent messages…</p>
                        ) : chvMessagesError ? (
                          <p className="mt-3 text-sm leading-6 text-status-danger">Unable to load recent messages right now.</p>
                        ) : chvMessages.length ? (
                          <div className="mt-3 space-y-3">
                            {chvMessages.slice(0, 3).map((message) => (
                              <div key={message.public_id} className="rounded-2xl border border-panel-table-wrap px-4 py-3">
                                <div className="flex flex-wrap items-start justify-between gap-3">
                                  <div>
                                    <strong className="text-sm text-panel-strong">{message.status.replace("_", " ")}</strong>
                                    <p className="mt-1 text-xs uppercase tracking-[0.14em] text-panel-subtle">
                                      {getChvMessageDeliveryTag(message.delivery_kind)}
                                    </p>
                                  </div>
                                  <span className="text-xs text-panel-muted">{formatRelativeTimestamp(message.created_at)}</span>
                                </div>
                                <p className="mt-2 text-sm leading-6 text-panel-copy">{message.message_body}</p>
                              </div>
                            ))}
                          </div>
                        ) : (
                          <p className="mt-3 text-sm leading-6 text-panel-muted">No CHV messages have been recorded yet.</p>
                        )}
                      </div>
                    </div>

                    <div className="mt-6 flex flex-wrap justify-end gap-3">
                      <Button type="button" variant="ghost" onClick={() => setIsChvMessageModalOpen(false)}>
                        Cancel
                      </Button>
                      <Button
                        type="button"
                        disabled={!messageBody.trim() || createChvMessageMutation.isPending}
                        onClick={async () => {
                          const result = await createChvMessageMutation.mutateAsync({
                            message_body: messageBody.trim(),
                            channel: "SMS",
                          });
                          setMessageFeedback(
                            result.status === "QUEUED"
                              ? "Message queued for follow-up."
                              : result.status === "FAILED"
                                ? "Message was recorded but delivery failed."
                                : selectedChv.messageDeliveryKind === "SIMULATED"
                                  ? "Message was sent through the stub provider."
                                  : "Message sent successfully.",
                          );
                          setSelectedMessageTemplateLabel(null);
                          setMessageBody("");
                        }}
                      >
                        {createChvMessageMutation.isPending
                          ? selectedChv.messageMode === "SEND"
                            ? "Sending..."
                            : "Queueing..."
                          : selectedChv.messageMode === "SEND"
                            ? "Send message"
                            : "Queue message"}
                      </Button>
                    </div>
                  </Card>
                </div>
              </>
            ) : null}
          </>
        ) : null}
      </RoleGate>
    </div>
  );
}
