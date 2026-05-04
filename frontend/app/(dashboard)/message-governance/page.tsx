"use client";

import {
  AlertTriangle,
  Ban,
  CheckCircle2,
  ClipboardCheck,
  Eye,
  Filter,
  History,
  Languages,
  MessageSquareText,
  RefreshCcw,
  Search,
  Send,
  ShieldCheck,
  Smartphone,
  UsersRound,
} from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, ReactNode, useEffect, useMemo, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { DashboardTopbar } from "@/components/dashboard-topbar";
import { RoleGate } from "@/components/role-gate";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { InputShell } from "@/components/ui/input-shell";
import { PageSectionHeader } from "@/components/ui/page-section-header";
import { StatusBadge } from "@/components/ui/status-badge";
import { cn } from "@/lib/cn";
import type {
  FetchMessageGovernanceParams,
  MessageDeliveryOutcomeRow,
  MessageDeliveryReachRow,
  MessageDeliveryTemplateRow,
  MessageOptOutMonitoringRow,
  MessageTemplateApprovalPayload,
  MessageTemplateRecord,
  UssdMenuVersionRecord,
} from "@/lib/dashboard";
import { formatRelativeTimestamp } from "@/lib/freshness";
import { MESSAGE_GOVERNANCE_ROLES, canApproveMessageTemplates } from "@/lib/roles";
import {
  useApproveMessageTemplateMutation,
  useMessageGovernanceDashboardQuery,
  useMessageTemplateDetailQuery,
} from "@/queries/use-message-governance-query";

type BadgeTone = "default" | "success" | "warning" | "danger" | "info";

function cleanParam(value: string | null) {
  return value?.trim() || undefined;
}

function paramsFromSearch(searchParams: URLSearchParams): FetchMessageGovernanceParams {
  return {
    q: cleanParam(searchParams.get("q")),
    audience_type: cleanParam(searchParams.get("audience_type")),
    channel: cleanParam(searchParams.get("channel")),
    language: cleanParam(searchParams.get("language")),
    approval_status: cleanParam(searchParams.get("approval_status")),
    date_from: cleanParam(searchParams.get("date_from")),
    date_to: cleanParam(searchParams.get("date_to")),
  };
}

function toTitleCase(value: string) {
  return value
    .toLowerCase()
    .split(/[\s_-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function formatTimestamp(timestamp: string | null | undefined) {
  if (!timestamp) return "Not set";
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return "Invalid date";
  return date.toLocaleString([], {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatPercent(value: number) {
  return `${value.toFixed(value >= 10 ? 1 : 2)}%`;
}

function filtersEqual(left: FetchMessageGovernanceParams, right: FetchMessageGovernanceParams) {
  const keys: Array<keyof FetchMessageGovernanceParams> = [
    "q",
    "audience_type",
    "channel",
    "language",
    "approval_status",
    "date_from",
    "date_to",
  ];
  return keys.every((key) => (left[key] ?? "") === (right[key] ?? ""));
}

function approvalTone(status: string): BadgeTone {
  if (status === "approved" || status === "APPROVED") return "success";
  if (status === "pending_review" || status === "draft" || status === "DRAFT") return "warning";
  if (status === "rejected" || status === "RETIRED") return "danger";
  if (status === "retired") return "default";
  return "info";
}

function riskTone(riskLevel: string): BadgeTone {
  if (riskLevel === "critical" || riskLevel === "high") return "danger";
  if (riskLevel === "medium") return "warning";
  return "info";
}

function SummaryTile({
  icon,
  label,
  value,
  tone = "info",
}: {
  icon: ReactNode;
  label: string;
  value: string | number;
  tone?: BadgeTone;
}) {
  const toneClass =
    tone === "success"
      ? "text-[color:var(--success)]"
      : tone === "warning"
        ? "text-[color:var(--warning)]"
        : tone === "danger"
          ? "text-[color:var(--danger)]"
          : "text-brand";

  return (
    <Card className="grid min-h-[8rem] gap-3 p-4">
      <span className={cn("inline-flex size-9 items-center justify-center rounded-2xl bg-[var(--dashboard-icon-button-surface)]", toneClass)}>
        {icon}
      </span>
      <div>
        <p className="text-2xl font-semibold text-panel-strong">{value}</p>
        <p className="text-sm text-panel-muted">{label}</p>
      </div>
    </Card>
  );
}

function TemplateList({
  templates,
  selectedPublicId,
  onSelect,
}: {
  templates: MessageTemplateRecord[];
  selectedPublicId: string | null;
  onSelect: (template: MessageTemplateRecord) => void;
}) {
  if (!templates.length) {
    return (
      <Card className="p-5">
        <p className="font-semibold text-panel-strong">No templates match the current filters</p>
      </Card>
    );
  }

  return (
    <div className="overflow-hidden rounded-panel border border-panel-table-wrap bg-panel">
      <div className="grid grid-cols-[1.4fr_0.7fr_0.7fr_0.8fr] gap-3 border-b border-[var(--dashboard-table-line)] px-4 py-3 text-sm font-semibold text-panel-muted max-[760px]:hidden">
        <span>Template</span>
        <span>Audience</span>
        <span>Language</span>
        <span>Status</span>
      </div>
      {templates.map((template) => (
        <button
          key={template.public_id}
          type="button"
          onClick={() => onSelect(template)}
          className={cn(
            "grid w-full grid-cols-[1.4fr_0.7fr_0.7fr_0.8fr] gap-3 border-b border-[var(--dashboard-table-line)] px-4 py-3 text-left text-sm transition last:border-b-0 max-[760px]:grid-cols-1",
            selectedPublicId === template.public_id
              ? "bg-[color-mix(in_srgb,var(--dashboard-sidebar-title)_10%,transparent)]"
              : "hover:bg-[color-mix(in_srgb,var(--dashboard-nav-hover)_72%,transparent)]",
          )}
        >
          <span className="min-w-0">
            <span className="block truncate font-semibold text-panel-strong">{template.title}</span>
            <span className="mt-1 block truncate text-xs text-panel-muted">
              {template.template_key} · v{template.version}
            </span>
          </span>
          <span className="text-panel-copy">{toTitleCase(template.audience_type)}</span>
          <span className="text-panel-copy">{template.language.toUpperCase()}</span>
          <span>
            <StatusBadge tone={approvalTone(template.approval_status)}>
              {toTitleCase(template.approval_status)}
            </StatusBadge>
          </span>
        </button>
      ))}
    </div>
  );
}

function TemplateDetailPanel({
  template,
  versionHistory,
  languageVariants,
  canApprove,
  onApprovalAction,
  isUpdating,
}: {
  template: MessageTemplateRecord | null;
  versionHistory: MessageTemplateRecord[];
  languageVariants: MessageTemplateRecord[];
  canApprove: boolean;
  onApprovalAction: (action: MessageTemplateApprovalPayload["action"], reason: string) => Promise<void>;
  isUpdating: boolean;
}) {
  const [reason, setReason] = useState("");
  const approvalEvents = Array.isArray(template?.lineage_metadata.approval_events)
    ? template?.lineage_metadata.approval_events as Array<Record<string, unknown>>
    : [];

  useEffect(() => {
    setReason("");
  }, [template?.public_id]);

  if (!template) {
    return (
      <Card className="p-5">
        <p className="font-semibold text-panel-strong">No template selected</p>
      </Card>
    );
  }

  async function submitApproval(action: MessageTemplateApprovalPayload["action"]) {
    await onApprovalAction(action, reason);
    setReason("");
  }

  return (
    <Card className="grid gap-5 p-5">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <p className="text-sm font-medium text-panel-muted">{template.template_key}</p>
          <h3 className="mt-1 text-xl font-semibold text-panel-strong">{template.title}</h3>
          <p className="mt-2 text-sm text-panel-muted">
            {template.owner} · v{template.version} · {template.language.toUpperCase()}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <StatusBadge tone={approvalTone(template.approval_status)}>{toTitleCase(template.approval_status)}</StatusBadge>
          <StatusBadge tone={riskTone(template.risk_level)}>{toTitleCase(template.risk_level)}</StatusBadge>
        </div>
      </div>

      <section className="grid gap-3">
        <div className="flex items-center gap-2">
          <Eye className="size-4 text-brand" />
          <h4 className="font-semibold text-panel-strong">Language Preview</h4>
        </div>
        <div className="rounded-2xl border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] p-4">
          <p className="whitespace-pre-wrap text-sm leading-6 text-panel-copy">{template.preview.rendered_body}</p>
        </div>
        {template.preview.declared_placeholders.length ? (
          <div className="flex flex-wrap gap-2">
            {template.preview.declared_placeholders.map((placeholder) => (
              <StatusBadge key={placeholder} tone="info">{placeholder}</StatusBadge>
            ))}
          </div>
        ) : null}
      </section>

      <section className="grid gap-3">
        <div className="flex items-center gap-2">
          <ShieldCheck className="size-4 text-brand" />
          <h4 className="font-semibold text-panel-strong">Audience Preview</h4>
        </div>
        <div className="grid gap-3 md:grid-cols-2">
          <div className="rounded-2xl border border-panel-table-wrap p-3">
            <p className="text-xs text-panel-muted">Audience</p>
            <p className="mt-1 font-semibold text-panel-strong">{toTitleCase(template.audience_preview.audience_type)}</p>
          </div>
          <div className="rounded-2xl border border-panel-table-wrap p-3">
            <p className="text-xs text-panel-muted">Consent rule</p>
            <p className="mt-1 font-semibold text-panel-strong">{toTitleCase(template.audience_preview.consent_requirement)}</p>
          </div>
        </div>
      </section>

      <section className="grid gap-3">
        <div className="flex items-center gap-2">
          <ClipboardCheck className="size-4 text-brand" />
          <h4 className="font-semibold text-panel-strong">Attribution</h4>
        </div>
        <div className="grid gap-3 md:grid-cols-3">
          <div className="rounded-2xl border border-panel-table-wrap p-3">
            <p className="text-xs text-panel-muted">Created by</p>
            <p className="mt-1 font-semibold text-panel-strong">{template.created_by_username || "Unknown"}</p>
            <p className="mt-1 text-xs text-panel-muted">{formatTimestamp(template.created_at)}</p>
          </div>
          <div className="rounded-2xl border border-panel-table-wrap p-3">
            <p className="text-xs text-panel-muted">Approved by</p>
            <p className="mt-1 font-semibold text-panel-strong">{template.approved_by_username || "Not approved"}</p>
            <p className="mt-1 text-xs text-panel-muted">{formatTimestamp(template.approved_at)}</p>
          </div>
          <div className="rounded-2xl border border-panel-table-wrap p-3">
            <p className="text-xs text-panel-muted">Updated</p>
            <p className="mt-1 font-semibold text-panel-strong">{formatTimestamp(template.updated_at)}</p>
            <p className="mt-1 text-xs text-panel-muted">{template.owner}</p>
          </div>
        </div>
      </section>

      <section className="grid gap-3">
        <div className="flex items-center gap-2">
          <History className="size-4 text-brand" />
          <h4 className="font-semibold text-panel-strong">Version History</h4>
        </div>
        <div className="grid gap-2">
          {versionHistory.map((version) => (
            <div key={version.public_id} className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-panel-table-wrap px-3 py-2 text-sm">
              <span className="font-semibold text-panel-strong">v{version.version}</span>
              <span className="text-panel-muted">{formatTimestamp(version.updated_at)}</span>
              <StatusBadge tone={approvalTone(version.approval_status)}>{toTitleCase(version.approval_status)}</StatusBadge>
            </div>
          ))}
        </div>
      </section>

      <section className="grid gap-3">
        <div className="flex items-center gap-2">
          <Languages className="size-4 text-brand" />
          <h4 className="font-semibold text-panel-strong">Language Variants</h4>
        </div>
        <div className="flex flex-wrap gap-2">
          {languageVariants.map((variant) => (
            <StatusBadge key={variant.public_id} tone={variant.public_id === template.public_id ? "success" : "default"}>
              {variant.language.toUpperCase()} v{variant.version}
            </StatusBadge>
          ))}
        </div>
      </section>

      <section className="grid gap-3 border-t border-[var(--dashboard-table-line)] pt-4">
        <div className="flex items-center gap-2">
          <ClipboardCheck className="size-4 text-brand" />
          <h4 className="font-semibold text-panel-strong">Approval Workflow</h4>
        </div>
        <textarea
          value={reason}
          onChange={(event) => setReason(event.target.value)}
          className="min-h-20 rounded-2xl border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] px-4 py-3 text-sm text-panel-strong outline-none"
          placeholder="Review note"
        />
        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            onClick={() => submitApproval("approve")}
            disabled={!canApprove || isUpdating}
          >
            <CheckCircle2 className="size-4" />
            Approve
          </Button>
          <Button
            type="button"
            variant="secondary"
            onClick={() => submitApproval("request_review")}
            disabled={!canApprove || isUpdating}
          >
            Request review
          </Button>
          <Button
            type="button"
            variant="secondary"
            onClick={() => submitApproval("retire")}
            disabled={!canApprove || isUpdating}
          >
            Retire
          </Button>
        </div>
        {canApprove ? null : (
          <p className="text-sm text-panel-muted">Approval actions are limited to administrators.</p>
        )}
        {approvalEvents.length ? (
          <div className="grid gap-2">
            {approvalEvents.slice(-3).reverse().map((event, index) => (
              <div key={`${String(event.created_at)}-${index}`} className="rounded-2xl border border-panel-table-wrap px-3 py-2 text-sm">
                <p className="font-semibold text-panel-strong">{toTitleCase(String(event.action ?? "review"))}</p>
                <p className="mt-1 text-panel-muted">
                  {String(event.actor_username ?? "unknown")} · {formatTimestamp(String(event.created_at ?? ""))}
                </p>
              </div>
            ))}
          </div>
        ) : null}
      </section>
    </Card>
  );
}

function DeliveryOutcomeTable({ rows }: { rows: MessageDeliveryOutcomeRow[] }) {
  if (!rows.length) {
    return (
      <Card className="p-5">
        <p className="font-semibold text-panel-strong">No delivery outcomes in range</p>
      </Card>
    );
  }

  return (
    <div className="overflow-hidden rounded-panel border border-panel-table-wrap bg-panel">
      <div className="grid grid-cols-[1fr_0.7fr_0.8fr_0.5fr] gap-3 border-b border-[var(--dashboard-table-line)] px-4 py-3 text-sm font-semibold text-panel-muted max-[760px]:hidden">
        <span>Audience</span>
        <span>Channel</span>
        <span>Status</span>
        <span>Count</span>
      </div>
      {rows.map((row) => (
        <div
          key={`${row.audience_type}-${row.channel}-${row.status}`}
          className="grid grid-cols-[1fr_0.7fr_0.8fr_0.5fr] gap-3 border-b border-[var(--dashboard-table-line)] px-4 py-3 text-sm last:border-b-0 max-[760px]:grid-cols-2"
        >
          <span className="font-semibold text-panel-strong">{toTitleCase(row.audience_type)}</span>
          <span className="text-panel-copy">{toTitleCase(row.channel)}</span>
          <span className="text-panel-copy">{toTitleCase(row.status)}</span>
          <span className="font-semibold text-panel-strong">{row.count}</span>
        </div>
      ))}
    </div>
  );
}

function CommunicationReachTable({ rows }: { rows: MessageDeliveryReachRow[] }) {
  if (!rows.length) {
    return (
      <Card className="p-5">
        <p className="font-semibold text-panel-strong">No communication reach in range</p>
      </Card>
    );
  }

  return (
    <div className="overflow-hidden rounded-panel border border-panel-table-wrap bg-panel">
      <div className="grid grid-cols-[1fr_0.7fr_0.6fr_0.6fr_0.7fr] gap-3 border-b border-[var(--dashboard-table-line)] px-4 py-3 text-sm font-semibold text-panel-muted max-[760px]:hidden">
        <span>Audience</span>
        <span>Channel</span>
        <span>Messages</span>
        <span>Reach</span>
        <span>Failures</span>
      </div>
      {rows.map((row) => (
        <div
          key={`${row.audience_type}-${row.channel}`}
          className="grid grid-cols-[1fr_0.7fr_0.6fr_0.6fr_0.7fr] gap-3 border-b border-[var(--dashboard-table-line)] px-4 py-3 text-sm last:border-b-0 max-[760px]:grid-cols-2"
        >
          <span className="font-semibold text-panel-strong">{toTitleCase(row.audience_type)}</span>
          <span className="text-panel-copy">{toTitleCase(row.channel)}</span>
          <span className="font-semibold text-panel-strong">{row.message_count}</span>
          <span className="text-panel-copy">{row.unique_recipient_count}</span>
          <span className={cn("font-semibold", row.failed_count > 0 ? "text-[color:var(--danger)]" : "text-panel-strong")}>
            {row.failed_count}
          </span>
        </div>
      ))}
    </div>
  );
}

function OptOutMonitoringTable({ rows }: { rows: MessageOptOutMonitoringRow[] }) {
  if (!rows.length) {
    return (
      <Card className="p-5">
        <p className="font-semibold text-panel-strong">No opt-out activity in range</p>
      </Card>
    );
  }

  return (
    <div className="overflow-hidden rounded-panel border border-panel-table-wrap bg-panel">
      <div className="grid grid-cols-[1fr_0.7fr_0.7fr_0.8fr] gap-3 border-b border-[var(--dashboard-table-line)] px-4 py-3 text-sm font-semibold text-panel-muted max-[760px]:hidden">
        <span>Audience</span>
        <span>Channel</span>
        <span>Opt-outs</span>
        <span>Blocked sends</span>
      </div>
      {rows.map((row) => (
        <div
          key={`${row.audience_type}-${row.channel}`}
          className="grid grid-cols-[1fr_0.7fr_0.7fr_0.8fr] gap-3 border-b border-[var(--dashboard-table-line)] px-4 py-3 text-sm last:border-b-0 max-[760px]:grid-cols-2"
        >
          <span className="font-semibold text-panel-strong">{toTitleCase(row.audience_type)}</span>
          <span className="text-panel-copy">{toTitleCase(row.channel)}</span>
          <span className="font-semibold text-panel-strong">{row.current_opt_out_count}</span>
          <span className="text-panel-copy">{row.blocked_opt_out_event_count}</span>
        </div>
      ))}
    </div>
  );
}

function TemplateUsageTable({ rows }: { rows: MessageDeliveryTemplateRow[] }) {
  if (!rows.length) {
    return (
      <Card className="p-5">
        <p className="font-semibold text-panel-strong">No template usage in range</p>
      </Card>
    );
  }

  return (
    <div className="overflow-hidden rounded-panel border border-panel-table-wrap bg-panel">
      <div className="grid grid-cols-[1.4fr_0.4fr_0.5fr_1fr] gap-3 border-b border-[var(--dashboard-table-line)] px-4 py-3 text-sm font-semibold text-panel-muted max-[760px]:hidden">
        <span>Template</span>
        <span>Version</span>
        <span>Count</span>
        <span>Status mix</span>
      </div>
      {rows.slice(0, 10).map((row) => (
        <div
          key={`${row.template_key}-${row.template_version ?? "unlinked"}`}
          className="grid grid-cols-[1.4fr_0.4fr_0.5fr_1fr] gap-3 border-b border-[var(--dashboard-table-line)] px-4 py-3 text-sm last:border-b-0 max-[760px]:grid-cols-1"
        >
          <span className="truncate font-semibold text-panel-strong">{row.template_key}</span>
          <span className="text-panel-copy">{row.template_version ? `v${row.template_version}` : "Unlinked"}</span>
          <span className="font-semibold text-panel-strong">{row.count}</span>
          <span className="flex flex-wrap gap-1">
            {Object.entries(row.statuses).map(([statusValue, count]) => (
              <StatusBadge key={statusValue} tone={statusValue === "FAILED" ? "danger" : "default"}>
                {toTitleCase(statusValue)} {count}
              </StatusBadge>
            ))}
          </span>
        </div>
      ))}
    </div>
  );
}

function UssdMenuVersionList({ menuVersions }: { menuVersions: UssdMenuVersionRecord[] }) {
  if (!menuVersions.length) {
    return (
      <Card className="p-5">
        <p className="font-semibold text-panel-strong">No USSD menu versions registered</p>
      </Card>
    );
  }

  return (
    <div className="grid gap-3">
      {menuVersions.slice(0, 8).map((version) => (
        <Card key={version.public_id} className="grid gap-3 p-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="font-semibold text-panel-strong">{version.title}</p>
              <p className="mt-1 text-sm text-panel-muted">
                {version.menu_key} · {version.version_label} · {version.language.toUpperCase()}
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <StatusBadge tone={approvalTone(version.approval_status)}>{toTitleCase(version.approval_status)}</StatusBadge>
              <StatusBadge tone={version.validation_status === "pass" ? "success" : "danger"}>
                {toTitleCase(version.validation_status)}
              </StatusBadge>
              {version.is_active ? <StatusBadge tone="info">Active</StatusBadge> : null}
            </div>
          </div>
          <div className="grid gap-2 text-sm text-panel-muted md:grid-cols-3">
            <span>{version.route_count} routes</span>
            <span>{version.node_count} nodes</span>
            <span>Fallback: {version.safe_fallback_copy}</span>
          </div>
        </Card>
      ))}
    </div>
  );
}

export default function MessageGovernancePage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const filters = useMemo(() => paramsFromSearch(searchParams), [searchParams]);
  const { currentUser } = useAuth();
  const { data, isPending, error, refetch, isFetching } = useMessageGovernanceDashboardQuery(filters);
  const approveMutation = useApproveMessageTemplateMutation();
  const [draftFilters, setDraftFilters] = useState(filters);
  const [selectedTemplateId, setSelectedTemplateId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const { data: selectedTemplateDetail } = useMessageTemplateDetailQuery(selectedTemplateId);

  const lastUpdatedLabel = data?.generated_at ? formatRelativeTimestamp(data.generated_at) : "No governance snapshot";
  const canApprove = canApproveMessageTemplates(currentUser?.role);

  useEffect(() => {
    setDraftFilters((current) => (filtersEqual(current, filters) ? current : filters));
  }, [filters]);

  useEffect(() => {
    if (!data?.templates.length) {
      setSelectedTemplateId(null);
      return;
    }
    if (!selectedTemplateId || !data.templates.some((template) => template.public_id === selectedTemplateId)) {
      setSelectedTemplateId(data.templates[0].public_id);
    }
  }, [data?.templates, selectedTemplateId]);

  const selectedTemplateFromList = data?.templates.find((template) => template.public_id === selectedTemplateId) ?? null;
  const selectedTemplate = selectedTemplateDetail?.template ?? selectedTemplateFromList;
  const fallbackVersionHistory = selectedTemplateFromList && data
    ? data.templates
        .filter((template) => template.template_key === selectedTemplateFromList.template_key && template.language === selectedTemplateFromList.language)
        .sort((left, right) => right.version - left.version)
    : [];
  const fallbackLanguageVariants = selectedTemplateFromList && data
    ? data.templates
        .filter((template) => template.template_key === selectedTemplateFromList.template_key && template.version === selectedTemplateFromList.version)
        .sort((left, right) => left.language.localeCompare(right.language))
    : [];
  const versionHistory = selectedTemplateDetail?.version_history ?? fallbackVersionHistory;
  const languageVariants = selectedTemplateDetail?.language_variants ?? fallbackLanguageVariants;

  function updateDraft(key: keyof FetchMessageGovernanceParams, value: string) {
    setDraftFilters((current) => ({ ...current, [key]: value || undefined }));
  }

  function applyFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const params = new URLSearchParams();
    for (const [key, value] of Object.entries(draftFilters)) {
      if (value !== undefined && value !== "") {
        params.set(key, String(value));
      }
    }
    router.push(`/message-governance${params.size ? `?${params.toString()}` : ""}`);
  }

  function resetFilters() {
    setDraftFilters({});
    router.push("/message-governance");
  }

  async function handleApprovalAction(action: MessageTemplateApprovalPayload["action"], reason: string) {
    if (!selectedTemplate) return;
    setActionError(null);
    setActionMessage(null);
    try {
      await approveMutation.mutateAsync({
        publicId: selectedTemplate.public_id,
        payload: { action, reason },
      });
      setActionMessage(`${toTitleCase(action)} saved for ${selectedTemplate.title}.`);
      await refetch();
    } catch (approvalError) {
      setActionError(approvalError instanceof Error ? approvalError.message : "Unable to update template approval.");
    }
  }

  return (
    <RoleGate
      allowedRoles={MESSAGE_GOVERNANCE_ROLES}
      title="Message governance unavailable"
      message="Your role cannot view public-health communication governance."
    >
      <div className="space-y-8">
        <DashboardTopbar
          title="Message Governance"
          subtitle="Templates, public-health copy approval, delivery outcomes, and USSD sessions."
          lastUpdatedLabel={lastUpdatedLabel}
          lastUpdatedTone={data?.summary.audit_status === "pass" ? "default" : "stale"}
          onRefresh={() => refetch()}
        />

        <PageSectionHeader
          title="Public-Health Communications"
          description="Versioned copy and delivery review across SMS, USSD, dashboard, and offline bundles."
          actions={
            <Button type="button" variant="secondary" onClick={() => refetch()} disabled={isFetching}>
              <RefreshCcw className={cn("size-4", isFetching && "animate-spin")} />
              Refresh
            </Button>
          }
        />

        <form
          onSubmit={applyFilters}
          className="grid gap-3 rounded-panel border border-panel-table-wrap bg-[color-mix(in_srgb,var(--dashboard-table-line)_14%,transparent)] p-4 lg:grid-cols-[1.2fr_repeat(5,minmax(0,0.8fr))_auto]"
        >
          <InputShell
            label="Search"
            value={draftFilters.q ?? ""}
            onChange={(event) => updateDraft("q", event.target.value)}
            icon={<Search className="size-4" />}
          />
          <label className="flex min-w-0 flex-col gap-1.5">
            <span className="text-sm font-medium text-panel-copy">Audience</span>
            <select
              className="h-10 rounded-pill border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] px-4 text-sm text-panel-strong outline-none"
              value={draftFilters.audience_type ?? ""}
              onChange={(event) => updateDraft("audience_type", event.target.value)}
            >
              <option value="">All</option>
              {data?.available_filters.audience_types.map((audience) => (
                <option key={audience} value={audience}>{toTitleCase(audience)}</option>
              ))}
            </select>
          </label>
          <label className="flex min-w-0 flex-col gap-1.5">
            <span className="text-sm font-medium text-panel-copy">Channel</span>
            <select
              className="h-10 rounded-pill border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] px-4 text-sm text-panel-strong outline-none"
              value={draftFilters.channel ?? ""}
              onChange={(event) => updateDraft("channel", event.target.value)}
            >
              <option value="">All</option>
              {data?.available_filters.channels.map((channel) => (
                <option key={channel} value={channel}>{toTitleCase(channel)}</option>
              ))}
            </select>
          </label>
          <label className="flex min-w-0 flex-col gap-1.5">
            <span className="text-sm font-medium text-panel-copy">Language</span>
            <select
              className="h-10 rounded-pill border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] px-4 text-sm text-panel-strong outline-none"
              value={draftFilters.language ?? ""}
              onChange={(event) => updateDraft("language", event.target.value)}
            >
              <option value="">All</option>
              {data?.available_filters.languages.map((language) => (
                <option key={language} value={language}>{language.toUpperCase()}</option>
              ))}
            </select>
          </label>
          <label className="flex min-w-0 flex-col gap-1.5">
            <span className="text-sm font-medium text-panel-copy">Status</span>
            <select
              className="h-10 rounded-pill border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] px-4 text-sm text-panel-strong outline-none"
              value={draftFilters.approval_status ?? ""}
              onChange={(event) => updateDraft("approval_status", event.target.value)}
            >
              <option value="">All</option>
              {data?.available_filters.approval_statuses.map((statusValue) => (
                <option key={statusValue} value={statusValue}>{toTitleCase(statusValue)}</option>
              ))}
            </select>
          </label>
          <div className="grid grid-cols-2 gap-2">
            <InputShell
              label="From"
              type="date"
              value={draftFilters.date_from ?? ""}
              onChange={(event) => updateDraft("date_from", event.target.value)}
            />
            <InputShell
              label="To"
              type="date"
              value={draftFilters.date_to ?? ""}
              onChange={(event) => updateDraft("date_to", event.target.value)}
            />
          </div>
          <div className="flex items-end gap-2">
            <Button type="submit">
              <Filter className="size-4" />
              Apply
            </Button>
            <Button type="button" variant="secondary" onClick={resetFilters}>
              Reset
            </Button>
          </div>
        </form>

        {error ? (
          <Card className="border-[color-mix(in_srgb,var(--danger)_28%,var(--dashboard-table-line))] p-5">
            <div className="flex items-start gap-3">
              <AlertTriangle className="mt-0.5 size-5 text-[color:var(--danger)]" />
              <div>
                <p className="font-semibold text-panel-strong">Unable to load message governance</p>
                <p className="mt-1 text-sm text-panel-muted">{error.message}</p>
              </div>
            </div>
          </Card>
        ) : null}

        {actionError ? (
          <Card className="border-[color-mix(in_srgb,var(--danger)_28%,var(--dashboard-table-line))] p-5">
            <p className="font-semibold text-panel-strong">Approval update failed</p>
            <p className="mt-1 text-sm text-panel-muted">{actionError}</p>
          </Card>
        ) : null}

        {actionMessage ? (
          <Card className="border-[color-mix(in_srgb,var(--success)_28%,var(--dashboard-table-line))] p-5">
            <p className="font-semibold text-panel-strong">{actionMessage}</p>
          </Card>
        ) : null}

        {isPending ? (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-6 2xl:grid-cols-9">
            {Array.from({ length: 9 }).map((_, index) => (
              <div
                key={index}
                className="h-32 animate-pulse rounded-panel border border-panel-table-wrap bg-[color-mix(in_srgb,var(--dashboard-table-line)_28%,transparent)]"
              />
            ))}
          </div>
        ) : data ? (
          <>
            <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-6 2xl:grid-cols-9">
              <SummaryTile icon={<MessageSquareText className="size-5" />} label="Templates" value={data.summary.template_count} />
              <SummaryTile icon={<CheckCircle2 className="size-5" />} label="Approved" value={data.summary.approved_template_count} tone="success" />
              <SummaryTile icon={<ClipboardCheck className="size-5" />} label="Pending review" value={data.summary.pending_review_template_count} tone="warning" />
              <SummaryTile icon={<UsersRound className="size-5" />} label="Reach" value={data.summary.communication_reach_count} />
              <SummaryTile icon={<Send className="size-5" />} label="Delivery success" value={formatPercent(data.summary.delivery_success_rate_pct)} tone="success" />
              <SummaryTile icon={<AlertTriangle className="size-5" />} label="Delivery failures" value={data.summary.delivery_failure_count} tone="danger" />
              <SummaryTile icon={<Ban className="size-5" />} label="Opt-outs" value={data.summary.opt_out_count} tone="warning" />
              <SummaryTile icon={<Smartphone className="size-5" />} label="USSD completion" value={formatPercent(data.summary.ussd_completion_rate_pct)} />
              <SummaryTile icon={<AlertTriangle className="size-5" />} label="Invalid USSD" value={formatPercent(data.summary.ussd_invalid_input_rate_pct)} tone="warning" />
            </section>

            <section className="grid gap-6 xl:grid-cols-[1.05fr_0.95fr]">
              <section className="grid content-start gap-4">
                <div className="flex items-center gap-3">
                  <MessageSquareText className="size-5 text-brand" />
                  <h3 className="text-lg font-semibold text-panel-strong">Template List</h3>
                </div>
                <TemplateList
                  templates={data.templates}
                  selectedPublicId={selectedTemplateId}
                  onSelect={(template) => setSelectedTemplateId(template.public_id)}
                />
              </section>

              <section className="grid content-start gap-4">
                <div className="flex items-center gap-3">
                  <Eye className="size-5 text-brand" />
                  <h3 className="text-lg font-semibold text-panel-strong">Template Detail</h3>
                </div>
                <TemplateDetailPanel
                  template={selectedTemplate}
                  versionHistory={versionHistory}
                  languageVariants={languageVariants}
                  canApprove={canApprove}
                  onApprovalAction={handleApprovalAction}
                  isUpdating={approveMutation.isPending}
                />
              </section>
            </section>

            <section className="grid gap-6 xl:grid-cols-2">
              <section className="grid content-start gap-4">
                <div className="flex items-center gap-3">
                  <UsersRound className="size-5 text-brand" />
                  <h3 className="text-lg font-semibold text-panel-strong">Communication Reach</h3>
                </div>
                <CommunicationReachTable rows={data.delivery_summary.reach_by_audience_channel} />
              </section>

              <section className="grid content-start gap-4">
                <div className="flex items-center gap-3">
                  <Ban className="size-5 text-brand" />
                  <h3 className="text-lg font-semibold text-panel-strong">Opt-Out Monitoring</h3>
                </div>
                <OptOutMonitoringTable rows={data.delivery_summary.opt_out_summary.by_audience_channel} />
              </section>
            </section>

            <section className="grid gap-6 xl:grid-cols-[0.95fr_1.05fr]">
              <section className="grid content-start gap-4">
                <div className="flex items-center gap-3">
                  <Send className="size-5 text-brand" />
                  <h3 className="text-lg font-semibold text-panel-strong">Delivery Outcome Summary</h3>
                </div>
                <DeliveryOutcomeTable rows={data.delivery_summary.by_audience_channel_status} />
              </section>

              <section className="grid content-start gap-4">
                <div className="flex items-center gap-3">
                  <Smartphone className="size-5 text-brand" />
                  <h3 className="text-lg font-semibold text-panel-strong">USSD Session Analytics</h3>
                </div>
                <div className="grid gap-3 md:grid-cols-3">
                  <SummaryTile icon={<CheckCircle2 className="size-5" />} label="Completed sessions" value={data.ussd_analytics.completed_sessions} tone="success" />
                  <SummaryTile icon={<AlertTriangle className="size-5" />} label="Invalid sessions" value={data.ussd_analytics.invalid_input_sessions} tone="warning" />
                  <SummaryTile icon={<History className="size-5" />} label="Abandoned sessions" value={data.ussd_analytics.abandoned_sessions} tone="danger" />
                </div>
                <div className="overflow-hidden rounded-panel border border-panel-table-wrap bg-panel">
                  {data.ussd_analytics.by_menu_version.slice(0, 8).map((row) => (
                    <div key={`${row.menu_key}-${row.menu_version_label}-${row.language}`} className="grid grid-cols-[1fr_0.6fr_0.6fr_0.6fr] gap-3 border-b border-[var(--dashboard-table-line)] px-4 py-3 text-sm last:border-b-0 max-[760px]:grid-cols-2">
                      <span className="font-semibold text-panel-strong">{row.menu_version_label}</span>
                      <span>{row.language.toUpperCase()}</span>
                      <span>{row.session_count} sessions</span>
                      <span>{row.invalid_input_count} invalid</span>
                    </div>
                  ))}
                </div>
              </section>
            </section>

            <section className="grid gap-4">
              <div className="flex items-center gap-3">
                <History className="size-5 text-brand" />
                <h3 className="text-lg font-semibold text-panel-strong">Template Usage by Version</h3>
              </div>
              <TemplateUsageTable rows={data.delivery_summary.template_usage_by_version} />
            </section>

            <section className="grid gap-4">
              <div className="flex items-center gap-3">
                <Languages className="size-5 text-brand" />
                <h3 className="text-lg font-semibold text-panel-strong">USSD Menu Versions</h3>
              </div>
              <UssdMenuVersionList menuVersions={data.ussd_menu_versions} />
            </section>
          </>
        ) : null}
      </div>
    </RoleGate>
  );
}
