"use client";

import {
  AlertTriangle,
  ArrowRight,
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
import { ComponentProps, FormEvent, ReactNode, useEffect, useMemo, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { DashboardTopbar } from "@/components/dashboard-topbar";
import { RoleGate } from "@/components/role-gate";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { InputShell } from "@/components/ui/input-shell";
import { PageSectionHeader } from "@/components/ui/page-section-header";
import { StatusBadge as BaseStatusBadge } from "@/components/ui/status-badge";
import { cn } from "@/lib/cn";
import type {
  FetchMessageGovernanceParams,
  LocalizationRolloutSnapshot,
  MessageLanguagePreviewRecord,
  MessageGovernanceDashboardResponse,
  MessageDeliveryOutcomeRow,
  MessageDeliveryReachRow,
  MessageDeliveryTemplateRow,
  MissingTranslationDashboardItem,
  OfflineGuidanceLanguagePreview,
  TemplateLanguageCoverageRow,
  MessageOptOutMonitoringRow,
  MessageTemplateApprovalPayload,
  MessageTemplateRecord,
  UssdMenuVersionApprovalPayload,
  UssdRouteTreePreviewRecord,
  UssdMenuVersionRecord,
} from "@/lib/dashboard";
import { formatRelativeTimestamp } from "@/lib/freshness";
import { MESSAGE_GOVERNANCE_ROLES, canApproveMessageTemplates } from "@/lib/roles";
import {
  useApproveMessageTemplateMutation,
  useApproveUssdMenuVersionMutation,
  useMessageGovernanceDashboardQuery,
  useMessageTemplateDetailQuery,
} from "@/queries/use-message-governance-query";

type BadgeTone = "default" | "success" | "warning" | "danger" | "info";
type MessageReviewTab = "attention" | "messages" | "languages" | "sending" | "phone";

function StatusBadge({ className, ...props }: ComponentProps<typeof BaseStatusBadge>) {
  return <BaseStatusBadge className={cn("normal-case tracking-normal", className)} {...props} />;
}

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

function languageLabel(language: string) {
  const labels: Record<string, string> = {
    en: "English",
    sw: "Kiswahili",
    luo: "Dholuo",
  };
  return labels[language] ?? language.toUpperCase();
}

function languageListLabel(languages: string[]) {
  if (!languages.length) return "No languages yet";
  return languages.map(languageLabel).join(", ");
}

function audienceLabel(value: string) {
  const labels: Record<string, string> = {
    chv: "CHVs",
    household: "Households",
    facility_contact: "Facility contacts",
    county_operator: "County teams",
    system_operator: "System teams",
  };
  return labels[value] ?? toTitleCase(value);
}

function channelLabel(value: string) {
  const labels: Record<string, string> = {
    sms: "SMS",
    ussd: "Phone menu",
    dashboard: "Dashboard",
    offline_chv_bundle: "Offline CHV guide",
  };
  return labels[value] ?? toTitleCase(value);
}

function statusLabel(value: string) {
  const normalized = value.toLowerCase();
  const labels: Record<string, string> = {
    approved: "Approved",
    approve: "Approved",
    pending_review: "Needs review",
    request_review: "Asked for changes",
    draft: "Draft",
    rejected: "Rejected",
    reject: "Rejected",
    retired: "Archived",
    retire: "Archived",
    pass: "Ready",
    fail: "Needs review",
    warning: "Check",
    missing: "Missing",
    source: "Main version",
    active: "Active",
    complete: "Complete",
    ready: "Ready",
    blocked: "Blocked",
    delivered: "Sent",
    failed: "Failed",
    retry_pending: "Retrying",
  };
  return labels[normalized] ?? toTitleCase(value);
}

function issueTypeLabel(value: string) {
  const labels: Record<string, string> = {
    missing_variant: "Missing language",
    placeholder_parity: "Message field check",
    translation_review: "Language review",
    missing_ussd_menu: "Missing phone menu",
    ussd_route_parity: "Phone menu mismatch",
    strict_localization: "Language issue",
  };
  return labels[value] ?? toTitleCase(value);
}

function surfaceLabel(value: string) {
  const labels: Record<string, string> = {
    chv_sms: "CHV text messages",
    ussd: "Phone menu",
    offline_sync: "Offline sync",
    offline_bundle: "Offline CHV guide",
  };
  return labels[value] ?? toTitleCase(value);
}

function consentLabel(value: string) {
  const labels: Record<string, string> = {
    consent_or_approved_lawful_basis: "Consent or approved public health basis",
    consent_required: "Consent required",
    emergency_allowed: "Emergency use allowed",
    not_required: "No separate consent needed",
  };
  return labels[value] ?? toTitleCase(value);
}

function teamLabel(value: string) {
  const labels: Record<string, string> = {
    county_health_promotion: "County health promotion",
    county_public_health: "County public health",
  };
  return labels[value] ?? toTitleCase(value);
}

function messageKeyLabel(value: string) {
  return toTitleCase(value.replace(/^cholera\./, "").replaceAll(".", " "))
    .replace(/\bChv\b/g, "CHV")
    .replace(/\bSms\b/g, "SMS");
}

function plainTitle(value: string) {
  const labels: Record<string, string> = {
    cholera_health_menu: "Cholera health phone menu",
  };
  return (labels[value] ?? toTitleCase(value.replaceAll("_", " "))).replace(/\bUSSD\b/g, "phone menu");
}

function rolloutStepLabel(value: string) {
  const labels: Record<string, string> = {
    ship_english_audit_with_required_language_gaps: "Check English messages",
    add_kiswahili_and_dholuo_drafts: "Add Kiswahili and Dholuo",
    approve_ussd_and_chv_high_risk_guidance: "Approve phone menus and high-risk CHV messages",
    enable_language_preference_for_pilot_ward: "Turn on language choices for the pilot ward",
    monitor_fallback_and_failure_rates: "Watch backup text and failed sends",
    expand_to_all_chv_users_after_audit_passes: "Expand to all CHVs after review",
  };
  return labels[value] ?? toTitleCase(value);
}

function humanIssueMessage(message: string, language?: string) {
  if (/Route tree differs from the active English source menu/i.test(message)) {
    return "This phone menu does not match the English version. Review it before rollout.";
  }

  const missingUssdMatch = message.match(/Missing active ([A-Za-z]+) USSD menu/i);
  if (missingUssdMatch) {
    return `The ${missingUssdMatch[1]} phone menu is not ready. People may see backup text instead.`;
  }

  if (/Missing .* variant before rollout/i.test(message)) {
    return `The ${language ? languageLabel(language) : "language"} message is missing. Add it before rollout.`;
  }

  return message
    .replace(/\bUSSD\b/g, "phone menu")
    .replace(/fallback/gi, "backup text")
    .replace(/variant/gi, "version")
    .replace(/parity/gi, "match");
}

function phoneMenuText(value: string) {
  return value.replace(/^(CON|END)\s+/i, "").trim();
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

function issueTone(severity: string): BadgeTone {
  if (severity === "high") return "danger";
  if (severity === "medium") return "warning";
  return "info";
}

function previewRowsFromVariants(languageVariants: MessageTemplateRecord[]): MessageLanguagePreviewRecord[] {
  const variantsByLanguage = new Map(languageVariants.map((variant) => [variant.language, variant]));
  const source = variantsByLanguage.get("en");
  return ["en", "sw", "luo"].map((language) => {
    const variant = variantsByLanguage.get(language);
    if (!variant) {
      return {
        language,
        label: languageLabel(language),
        exists: false,
        public_id: "",
        title: "",
        approval_status: "",
        translation_status: "",
        source_template: source?.public_id ?? "",
        source_template_key: source?.template_key ?? "",
        source_template_version: source?.version ?? null,
        body: "",
        rendered_body: "",
        delivery_rendered_body: source?.preview.rendered_body ?? "",
        requested_language: language,
        resolved_language: source?.language ?? "",
        fallback_used: Boolean(source),
        placeholders: [],
        placeholder_parity_status: "missing",
        placeholder_warnings: [`Missing ${languageLabel(language)} variant.`],
        render_error: "",
      };
    }
    return {
      language,
      label: languageLabel(language),
      exists: true,
      public_id: variant.public_id,
      title: variant.title,
      approval_status: variant.approval_status,
      translation_status: variant.translation_status ?? "",
      source_template: variant.source_template ?? "",
      source_template_key: variant.source_template_key ?? "",
      source_template_version: variant.source_template_version ?? null,
      body: variant.body,
      rendered_body: variant.preview.rendered_body,
      delivery_rendered_body: variant.preview.rendered_body,
      requested_language: language,
      resolved_language: language,
      fallback_used: false,
      placeholders: variant.preview.declared_placeholders,
      placeholder_parity_status: language === "en" ? "source" : "pass",
      placeholder_warnings: [],
      render_error: variant.preview.render_error,
    };
  });
}

function SummaryTile({
  icon,
  label,
  value,
  helper,
  tone = "info",
}: {
  icon: ReactNode;
  label: string;
  value: string | number;
  helper?: string;
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
        {helper ? <p className="mt-1 text-xs leading-5 text-panel-muted">{helper}</p> : null}
      </div>
    </Card>
  );
}

function SectionTitle({ icon, title }: { icon: ReactNode; title: string }) {
  return (
    <div className="flex items-center gap-3">
      <span className="text-brand">{icon}</span>
      <h3 className="text-lg font-semibold text-panel-strong">{title}</h3>
    </div>
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
        <p className="font-semibold text-panel-strong">No messages match the current filters</p>
      </Card>
    );
  }

  return (
    <div className="overflow-hidden rounded-panel border border-panel-table-wrap bg-panel">
      <div className="grid grid-cols-[1.4fr_0.7fr_0.7fr_0.8fr] gap-3 border-b border-[var(--dashboard-table-line)] px-4 py-3 text-sm font-semibold text-panel-muted max-[760px]:hidden">
        <span>Message</span>
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
              {channelLabel(template.channel)} · version {template.version}
            </span>
          </span>
          <span className="text-panel-copy">{audienceLabel(template.audience_type)}</span>
          <span className="text-panel-copy">{languageLabel(template.language)}</span>
          <span>
            <StatusBadge tone={approvalTone(template.approval_status)}>
              {statusLabel(template.approval_status)}
            </StatusBadge>
          </span>
        </button>
      ))}
    </div>
  );
}

function SideBySideLanguagePreview({ rows }: { rows: MessageLanguagePreviewRecord[] }) {
  if (!rows.length) {
    return (
      <Card className="p-5">
        <p className="font-semibold text-panel-strong">No message text available</p>
      </Card>
    );
  }

  return (
    <section className="grid gap-3">
      <div className="flex items-center gap-2">
        <Eye className="size-4 text-brand" />
        <h4 className="font-semibold text-panel-strong">Message Text</h4>
      </div>
      <div className="grid gap-3 xl:grid-cols-3">
        {rows.map((row) => (
          <div key={row.language} className="grid min-h-[13rem] gap-3 rounded-2xl border border-panel-table-wrap p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <p className="font-semibold text-panel-strong">{row.label}</p>
                <p className="text-xs text-panel-muted">{row.language.toUpperCase()}</p>
              </div>
              <div className="flex flex-wrap gap-1">
                <StatusBadge tone={row.exists ? approvalTone(row.approval_status) : "danger"}>
                  {row.exists ? statusLabel(row.approval_status) : "Missing"}
                </StatusBadge>
                <StatusBadge tone={row.placeholder_parity_status === "warning" || row.placeholder_parity_status === "missing" ? "warning" : "success"}>
                  {statusLabel(row.placeholder_parity_status)}
                </StatusBadge>
              </div>
            </div>
            <div className="rounded-2xl border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] p-3">
              <p className="whitespace-pre-wrap text-sm leading-6 text-panel-copy">
                {row.rendered_body || row.delivery_rendered_body || "No preview text available."}
              </p>
            </div>
            {row.fallback_used && row.delivery_rendered_body ? (
              <div className="rounded-2xl border border-[color-mix(in_srgb,var(--warning)_38%,var(--dashboard-table-line))] bg-[color-mix(in_srgb,var(--warning)_8%,transparent)] p-3">
                <p className="text-xs font-semibold text-panel-muted">Backup text sent</p>
                <p className="mt-1 whitespace-pre-wrap text-sm leading-6 text-panel-copy">{row.delivery_rendered_body}</p>
              </div>
            ) : null}
            {row.placeholders.length ? (
              <div className="grid gap-1">
                <p className="text-xs font-semibold text-panel-muted">Fields used</p>
                <div className="flex flex-wrap gap-1">
                  {row.placeholders.map((placeholder) => (
                    <StatusBadge key={placeholder} tone="info">{placeholder}</StatusBadge>
                  ))}
                </div>
              </div>
            ) : null}
            {row.placeholder_warnings.length ? (
              <div className="grid gap-1">
                <p className="text-xs font-semibold text-panel-muted">Message fields</p>
                {row.placeholder_warnings.map((warning, index) => (
                  <p key={`${row.language}-warning-${index}`} className="text-xs leading-5 text-[color:var(--warning)]">
                    {humanIssueMessage(warning, row.language)}
                  </p>
                ))}
              </div>
            ) : null}
          </div>
        ))}
      </div>
    </section>
  );
}

function TemplateDetailPanel({
  template,
  versionHistory,
  languageVariants,
  sideBySidePreview,
  canApprove,
  onApprovalAction,
  isUpdating,
}: {
  template: MessageTemplateRecord | null;
  versionHistory: MessageTemplateRecord[];
  languageVariants: MessageTemplateRecord[];
  sideBySidePreview: MessageLanguagePreviewRecord[];
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
        <p className="font-semibold text-panel-strong">No message selected</p>
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
          <p className="text-sm font-medium text-panel-muted">
            {channelLabel(template.channel)} for {audienceLabel(template.audience_type)}
          </p>
          <h3 className="mt-1 text-xl font-semibold text-panel-strong">{template.title}</h3>
          <p className="mt-2 text-sm text-panel-muted">
            {teamLabel(template.owner)} · version {template.version} · {languageLabel(template.language)}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <StatusBadge tone={approvalTone(template.approval_status)}>{statusLabel(template.approval_status)}</StatusBadge>
          <StatusBadge tone={riskTone(template.risk_level)}>{toTitleCase(template.risk_level)} risk</StatusBadge>
        </div>
      </div>

      <SideBySideLanguagePreview rows={sideBySidePreview} />

      <section className="grid gap-3">
        <div className="flex items-center gap-2">
          <ShieldCheck className="size-4 text-brand" />
          <h4 className="font-semibold text-panel-strong">Who Will Receive It</h4>
        </div>
        <div className="grid gap-3 md:grid-cols-2">
          <div className="rounded-2xl border border-panel-table-wrap p-3">
            <p className="text-xs text-panel-muted">Audience</p>
            <p className="mt-1 font-semibold text-panel-strong">{audienceLabel(template.audience_preview.audience_type)}</p>
          </div>
          <div className="rounded-2xl border border-panel-table-wrap p-3">
            <p className="text-xs text-panel-muted">Permission</p>
            <p className="mt-1 font-semibold text-panel-strong">{consentLabel(template.audience_preview.consent_requirement)}</p>
          </div>
        </div>
      </section>

      <section className="grid gap-3">
        <div className="flex items-center gap-2">
          <ClipboardCheck className="size-4 text-brand" />
          <h4 className="font-semibold text-panel-strong">Review Trail</h4>
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
            <p className="mt-1 text-xs text-panel-muted">{teamLabel(template.owner)}</p>
          </div>
        </div>
      </section>

      <section className="grid gap-3">
        <div className="flex items-center gap-2">
          <History className="size-4 text-brand" />
          <h4 className="font-semibold text-panel-strong">Past Versions</h4>
        </div>
        <div className="grid gap-2">
          {versionHistory.map((version) => (
            <div key={version.public_id} className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-panel-table-wrap px-3 py-2 text-sm">
              <span className="font-semibold text-panel-strong">Version {version.version}</span>
              <span className="text-panel-muted">{formatTimestamp(version.updated_at)}</span>
              <StatusBadge tone={approvalTone(version.approval_status)}>{statusLabel(version.approval_status)}</StatusBadge>
            </div>
          ))}
        </div>
      </section>

      <section className="grid gap-3">
        <div className="flex items-center gap-2">
          <Languages className="size-4 text-brand" />
          <h4 className="font-semibold text-panel-strong">Language Versions</h4>
        </div>
        <div className="flex flex-wrap gap-2">
          {languageVariants.map((variant) => (
            <StatusBadge key={variant.public_id} tone={variant.public_id === template.public_id ? "success" : "default"}>
              {languageLabel(variant.language)} v{variant.version}
            </StatusBadge>
          ))}
        </div>
      </section>

      <section className="grid gap-3 border-t border-[var(--dashboard-table-line)] pt-4">
        <div className="flex items-center gap-2">
          <ClipboardCheck className="size-4 text-brand" />
          <h4 className="font-semibold text-panel-strong">Review Decision</h4>
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
            Ask for changes
          </Button>
          <Button
            type="button"
            variant="danger"
            onClick={() => submitApproval("reject")}
            disabled={!canApprove || isUpdating}
          >
            Reject
          </Button>
          <Button
            type="button"
            variant="secondary"
            onClick={() => submitApproval("retire")}
            disabled={!canApprove || isUpdating}
          >
            Archive
          </Button>
        </div>
        {canApprove ? null : (
          <p className="text-sm text-panel-muted">Only admins can approve, reject, or archive messages.</p>
        )}
        {approvalEvents.length ? (
          <div className="grid gap-2">
            {approvalEvents.slice(-3).reverse().map((event, index) => (
              <div key={`${String(event.created_at)}-${index}`} className="rounded-2xl border border-panel-table-wrap px-3 py-2 text-sm">
                <p className="font-semibold text-panel-strong">{statusLabel(String(event.action ?? "review"))}</p>
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
        <p className="font-semibold text-panel-strong">No sending results in this range</p>
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
          <span className="font-semibold text-panel-strong">{audienceLabel(row.audience_type)}</span>
          <span className="text-panel-copy">{channelLabel(row.channel)}</span>
          <span className="text-panel-copy">{statusLabel(row.status)}</span>
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
        <p className="font-semibold text-panel-strong">No reach data in this range</p>
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
          <span className="font-semibold text-panel-strong">{audienceLabel(row.audience_type)}</span>
          <span className="text-panel-copy">{channelLabel(row.channel)}</span>
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
        <p className="font-semibold text-panel-strong">No one stopped messages in this range</p>
      </Card>
    );
  }

  return (
    <div className="overflow-hidden rounded-panel border border-panel-table-wrap bg-panel">
      <div className="grid grid-cols-[1fr_0.7fr_0.7fr_0.8fr] gap-3 border-b border-[var(--dashboard-table-line)] px-4 py-3 text-sm font-semibold text-panel-muted max-[760px]:hidden">
        <span>Audience</span>
        <span>Channel</span>
        <span>Stopped messages</span>
        <span>Blocked sends</span>
      </div>
      {rows.map((row) => (
        <div
          key={`${row.audience_type}-${row.channel}`}
          className="grid grid-cols-[1fr_0.7fr_0.7fr_0.8fr] gap-3 border-b border-[var(--dashboard-table-line)] px-4 py-3 text-sm last:border-b-0 max-[760px]:grid-cols-2"
        >
          <span className="font-semibold text-panel-strong">{audienceLabel(row.audience_type)}</span>
          <span className="text-panel-copy">{channelLabel(row.channel)}</span>
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
        <p className="font-semibold text-panel-strong">No message use in this range</p>
      </Card>
    );
  }

  return (
    <div className="overflow-hidden rounded-panel border border-panel-table-wrap bg-panel">
      <div className="grid grid-cols-[1.4fr_0.4fr_0.5fr_1fr] gap-3 border-b border-[var(--dashboard-table-line)] px-4 py-3 text-sm font-semibold text-panel-muted max-[760px]:hidden">
        <span>Message</span>
        <span>Version</span>
        <span>Count</span>
        <span>Status mix</span>
      </div>
      {rows.slice(0, 10).map((row) => (
        <div
          key={`${row.template_key}-${row.template_version ?? "unlinked"}`}
          className="grid grid-cols-[1.4fr_0.4fr_0.5fr_1fr] gap-3 border-b border-[var(--dashboard-table-line)] px-4 py-3 text-sm last:border-b-0 max-[760px]:grid-cols-1"
        >
          <span className="truncate font-semibold text-panel-strong">{messageKeyLabel(row.template_key)}</span>
          <span className="text-panel-copy">{row.template_version ? `Version ${row.template_version}` : "Not linked"}</span>
          <span className="font-semibold text-panel-strong">{row.count}</span>
          <span className="flex flex-wrap gap-1">
            {Object.entries(row.statuses).map(([statusValue, count]) => (
              <StatusBadge key={statusValue} tone={statusValue === "FAILED" ? "danger" : "default"}>
                {statusLabel(statusValue)} {count}
              </StatusBadge>
            ))}
          </span>
        </div>
      ))}
    </div>
  );
}

function LanguageCoverageMatrix({ rows }: { rows: TemplateLanguageCoverageRow[] }) {
  if (!rows.length) {
    return (
      <Card className="p-5">
        <p className="font-semibold text-panel-strong">No language readiness rows yet</p>
      </Card>
    );
  }

  return (
    <div className="overflow-hidden rounded-panel border border-panel-table-wrap bg-panel">
      <div className="grid grid-cols-[1.25fr_0.55fr_1fr_1fr] gap-3 border-b border-[var(--dashboard-table-line)] px-4 py-3 text-sm font-semibold text-panel-muted max-[860px]:hidden">
        <span>Message</span>
        <span>Version</span>
        <span>Coverage</span>
        <span>Notes</span>
      </div>
      {rows.slice(0, 12).map((row) => (
        <div
          key={`${row.template_key}-${row.version}`}
          className="grid grid-cols-[1.25fr_0.55fr_1fr_1fr] gap-3 border-b border-[var(--dashboard-table-line)] px-4 py-3 text-sm last:border-b-0 max-[860px]:grid-cols-1"
        >
          <span className="min-w-0">
            <span className="block truncate font-semibold text-panel-strong">{row.title}</span>
            <span className="mt-1 block truncate text-xs text-panel-muted">{channelLabel(row.channel)} · {audienceLabel(row.audience_type)}</span>
          </span>
          <span className="text-panel-copy">Version {row.version}</span>
          <span className="flex flex-wrap gap-1">
            {row.variants.map((variant) => (
              <StatusBadge
                key={variant.language}
                tone={variant.exists ? (variant.placeholder_parity_status === "warning" ? "warning" : "success") : "danger"}
              >
                {variant.label}
              </StatusBadge>
            ))}
          </span>
          <span className="grid gap-1">
            {row.missing_language_labels.length ? (
              <span className="text-[color:var(--danger)]">
                Missing {row.missing_language_labels.join(", ")}
              </span>
            ) : null}
            {row.placeholder_warnings.length ? (
              <span className="text-[color:var(--warning)]">
                Message field checks {row.placeholder_warnings.length}
              </span>
            ) : null}
            {row.translation_review_warnings.length ? (
              <span className="text-[color:var(--warning)]">
                Language review notes {row.translation_review_warnings.length}
              </span>
            ) : null}
            {!row.missing_language_labels.length && !row.placeholder_warnings.length && !row.translation_review_warnings.length ? (
              <span className="text-panel-muted">No warnings</span>
            ) : null}
          </span>
        </div>
      ))}
    </div>
  );
}

function MissingTranslationDashboardPanel({ items }: { items: MissingTranslationDashboardItem[] }) {
  if (!items.length) {
    return (
      <Card className="p-5">
        <p className="font-semibold text-panel-strong">No language items need review</p>
      </Card>
    );
  }

  return (
    <div className="grid gap-3">
      {items.slice(0, 8).map((item, index) => (
        <Card key={`${item.issue_type}-${item.template_key}-${item.language}-${index}`} className="grid gap-2 p-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="truncate font-semibold text-panel-strong">{plainTitle(item.title)}</p>
              <p className="mt-1 text-sm text-panel-muted">
                {[channelLabel(item.channel), item.version_label?.trim() || (item.version ? `version ${item.version}` : ""), item.label]
                  .filter(Boolean)
                  .join(" · ")}
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <StatusBadge tone={issueTone(item.severity)}>{toTitleCase(item.severity)} priority</StatusBadge>
              <StatusBadge tone="info">{issueTypeLabel(item.issue_type)}</StatusBadge>
            </div>
          </div>
          <p className="text-sm leading-6 text-panel-copy">{humanIssueMessage(item.message, item.language)}</p>
        </Card>
      ))}
    </div>
  );
}

function LocalizationRolloutPanel({ rollout, strictIssueCount }: { rollout: LocalizationRolloutSnapshot; strictIssueCount: number }) {
  const fallbackMetrics = rollout.fallback_metrics.length
    ? rollout.fallback_metrics
    : [rollout.offline_bundle_requests_by_language].filter(Boolean);

  return (
    <Card className="grid gap-4 p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-sm font-medium text-panel-muted">Rollout readiness</p>
          <h3 className="mt-1 text-lg font-semibold text-panel-strong">Language Rollout</h3>
        </div>
        <div className="flex flex-wrap gap-2">
          <StatusBadge tone={strictIssueCount ? "danger" : "success"}>
            {strictIssueCount ? `${strictIssueCount} language issues` : "Ready"}
          </StatusBadge>
          <StatusBadge tone={rollout.fallback_rate_pct ? "warning" : "success"}>
            Backup text {formatPercent(rollout.fallback_rate_pct)}
          </StatusBadge>
        </div>
      </div>

      <div className="grid gap-3 md:grid-cols-3">
        <div className="rounded-2xl border border-panel-table-wrap p-3">
          <p className="text-xs text-panel-muted">Active CHVs</p>
          <p className="mt-1 text-xl font-semibold text-panel-strong">{rollout.active_chv_count}</p>
          <p className="mt-1 text-xs text-panel-muted">
            {rollout.chv_preferred_language_counts.map((item) => `${languageLabel(item.key)} ${item.count}`).join(" · ") || "No language preferences"}
          </p>
        </div>
        <div className="rounded-2xl border border-panel-table-wrap p-3">
          <p className="text-xs text-panel-muted">Missing language messages</p>
          <p className="mt-1 text-xl font-semibold text-panel-strong">{rollout.missing_translation_count}</p>
          <p className="mt-1 text-xs text-panel-muted">Items that must be fixed before rollout</p>
        </div>
        <div className="rounded-2xl border border-panel-table-wrap p-3">
          <p className="text-xs text-panel-muted">Waiting review</p>
          <p className="mt-1 text-xl font-semibold text-panel-strong">{rollout.translation_review_age.max_age_days}d</p>
          <p className="mt-1 text-xs text-panel-muted">
            {rollout.translation_review_age.pending_review_count} language messages awaiting review
          </p>
        </div>
      </div>

      <div className="grid gap-3 xl:grid-cols-[0.95fr_1.05fr]">
        <div className="grid gap-2">
          <p className="text-sm font-semibold text-panel-strong">Backup Text Use</p>
          {fallbackMetrics.map((metric) => (
            <div key={metric.surface} className="grid gap-1 rounded-2xl border border-panel-table-wrap px-3 py-2 text-sm">
              <div className="grid grid-cols-[1fr_auto_auto] gap-3">
                <span className="font-semibold text-panel-strong">{surfaceLabel(metric.surface)}</span>
                <span className="text-panel-muted">{metric.fallback_count}/{metric.total_count}</span>
                <span className={metric.fallback_count ? "text-[color:var(--warning)]" : "text-panel-copy"}>
                  {formatPercent(metric.fallback_rate_pct)}
                </span>
              </div>
              <p className="text-xs text-panel-muted">
                Requested {metric.by_requested_language.map((item) => `${languageLabel(item.key)} ${item.count}`).join(" · ") || "none"}
              </p>
            </div>
          ))}
        </div>
        <div className="grid gap-2">
          <p className="text-sm font-semibold text-panel-strong">Rollout Checklist</p>
          {rollout.rollout_path.map((step) => (
            <div key={step.step} className="flex flex-wrap items-center justify-between gap-2 rounded-2xl border border-panel-table-wrap px-3 py-2 text-sm">
              <span className="font-semibold text-panel-strong">{rolloutStepLabel(step.step)}</span>
              <StatusBadge tone={step.status === "complete" || step.status === "active" || step.status === "ready" ? "success" : step.status === "blocked" ? "danger" : "warning"}>
                {statusLabel(step.status)}
              </StatusBadge>
            </div>
          ))}
        </div>
      </div>
    </Card>
  );
}

function UssdRouteTreePreview({ previews }: { previews: UssdRouteTreePreviewRecord[] }) {
  if (!previews.length) {
    return (
      <Card className="p-5">
        <p className="font-semibold text-panel-strong">No phone menu preview is available</p>
      </Card>
    );
  }

  return (
    <div className="grid gap-4">
      {previews.map((preview) => (
        <Card key={preview.menu_key} className="grid gap-4 p-4">
          <div>
            <p className="font-semibold text-panel-strong">{preview.source_title || "Phone menu"}</p>
            <p className="mt-1 text-sm text-panel-muted">{preview.source_version_label || "No approved version yet"}</p>
          </div>
          <div className="grid gap-3 xl:grid-cols-3">
            {preview.languages.map((languagePreview) => (
              <div key={languagePreview.language} className="grid gap-3 rounded-2xl border border-panel-table-wrap p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="font-semibold text-panel-strong">{languagePreview.label}</p>
                  <div className="flex flex-wrap gap-1">
                    <StatusBadge tone={languagePreview.exists ? "success" : "danger"}>
                      {languagePreview.exists ? "Ready" : "Backup text"}
                    </StatusBadge>
                    {languagePreview.warnings.length ? <StatusBadge tone="warning">Needs review</StatusBadge> : null}
                  </div>
                </div>
                <div className="grid gap-2">
                  {languagePreview.routes.length ? (
                    languagePreview.routes.slice(0, 4).map((route) => (
                      <div key={`${languagePreview.language}-${route.route_label}`} className="rounded-2xl border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] p-3">
                        <p className="text-xs font-semibold text-panel-muted">Menu step</p>
                        <p className="mt-1 whitespace-pre-wrap text-sm leading-6 text-panel-copy">{phoneMenuText(route.body || route.response_text)}</p>
                      </div>
                    ))
                  ) : (
                    <div className="rounded-2xl border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] p-3">
                      <p className="text-sm leading-6 text-panel-copy">No approved {languagePreview.label} phone menu yet.</p>
                    </div>
                  )}
                </div>
                {languagePreview.warnings.length ? (
                  <div className="grid gap-1">
                    {languagePreview.warnings.map((warning, index) => (
                      <p key={`${languagePreview.language}-phone-warning-${index}`} className="text-xs leading-5 text-[color:var(--warning)]">
                        {humanIssueMessage(warning, languagePreview.language)}
                      </p>
                    ))}
                  </div>
                ) : null}
                {phoneMenuText(languagePreview.safe_fallback_copy) ? (
                  <p className="text-xs text-panel-muted">Backup text: {phoneMenuText(languagePreview.safe_fallback_copy)}</p>
                ) : null}
              </div>
            ))}
          </div>
        </Card>
      ))}
    </div>
  );
}

function OfflineGuidancePreview({ previews }: { previews: OfflineGuidanceLanguagePreview[] }) {
  if (!previews.length) {
    return (
      <Card className="p-5">
        <p className="font-semibold text-panel-strong">No CHV guide preview is available</p>
      </Card>
    );
  }

  return (
    <div className="grid gap-3 xl:grid-cols-3">
      {previews.map((preview) => (
        <Card key={preview.language} className="grid gap-3 p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <p className="font-semibold text-panel-strong">{preview.label}</p>
              <p className="text-sm text-panel-muted">
                {preview.item_count} items in {languageLabel(preview.resolved_language)}
              </p>
            </div>
            {preview.fallback_used ? <StatusBadge tone="warning">Backup text</StatusBadge> : <StatusBadge tone="success">Ready</StatusBadge>}
          </div>
          <div className="grid gap-2">
            {preview.items.slice(0, 3).map((item) => (
              <div key={`${preview.language}-${item.guidance_public_id}`} className="rounded-2xl border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] p-3">
                <p className="text-xs font-semibold uppercase text-panel-muted">{item.title}</p>
                <p className="mt-1 whitespace-pre-wrap text-sm leading-6 text-panel-copy">{item.rendered_body}</p>
              </div>
            ))}
          </div>
          {preview.warnings.length ? (
            <p className="text-xs leading-5 text-[color:var(--warning)]">
              {preview.warnings.map((warning) => humanIssueMessage(warning, preview.language)).join(" ")}
            </p>
          ) : null}
        </Card>
      ))}
    </div>
  );
}

function UssdMenuVersionList({
  menuVersions,
  canApprove,
  isUpdating,
  onApprovalAction,
}: {
  menuVersions: UssdMenuVersionRecord[];
  canApprove: boolean;
  isUpdating: boolean;
  onApprovalAction: (
    publicId: string,
    title: string,
    action: UssdMenuVersionApprovalPayload["action"],
  ) => void;
}) {
  if (!menuVersions.length) {
    return (
      <Card className="p-5">
        <p className="font-semibold text-panel-strong">No phone menu updates yet</p>
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
                {version.version_label} · {languageLabel(version.language)}
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <StatusBadge tone={approvalTone(version.approval_status)}>{statusLabel(version.approval_status)}</StatusBadge>
              <StatusBadge tone={version.validation_status === "pass" ? "success" : "danger"}>
                {statusLabel(version.validation_status)}
              </StatusBadge>
              {version.is_active ? <StatusBadge tone="info">Active</StatusBadge> : null}
            </div>
          </div>
          <div className="grid gap-2 text-sm text-panel-muted md:grid-cols-3">
            <span>{version.route_count} menu paths</span>
            <span>{version.node_count} menu screens</span>
            <span>Backup text: {phoneMenuText(version.safe_fallback_copy)}</span>
          </div>
          {canApprove ? (
            <div className="flex flex-wrap gap-2">
              <Button
                size="sm"
                onClick={() => onApprovalAction(version.public_id, version.title, "approve")}
                disabled={isUpdating || version.approval_status === "APPROVED"}
              >
                Approve
              </Button>
              <Button
                size="sm"
                variant="secondary"
                onClick={() => onApprovalAction(version.public_id, version.title, "request_review")}
                disabled={isUpdating}
              >
                Ask for changes
              </Button>
              <Button
                size="sm"
                variant="secondary"
                onClick={() => onApprovalAction(version.public_id, version.title, "reject")}
                disabled={isUpdating}
              >
                Reject
              </Button>
              <Button
                size="sm"
                variant="danger"
                onClick={() => onApprovalAction(version.public_id, version.title, "retire")}
                disabled={isUpdating || version.approval_status === "RETIRED"}
              >
                Archive
              </Button>
            </div>
          ) : null}
        </Card>
      ))}
    </div>
  );
}

function ReviewTabs({
  activeTab,
  onChange,
}: {
  activeTab: MessageReviewTab;
  onChange: (tab: MessageReviewTab) => void;
}) {
  const tabs: Array<{ id: MessageReviewTab; label: string; icon: ReactNode }> = [
    { id: "attention", label: "Needs Attention", icon: <AlertTriangle className="size-4" /> },
    { id: "messages", label: "Messages", icon: <MessageSquareText className="size-4" /> },
    { id: "languages", label: "Languages", icon: <Languages className="size-4" /> },
    { id: "sending", label: "Sending Results", icon: <Send className="size-4" /> },
    { id: "phone", label: "Phone Menus", icon: <Smartphone className="size-4" /> },
  ];

  return (
    <div className="flex gap-2 overflow-x-auto rounded-panel border border-panel-table-wrap bg-[color-mix(in_srgb,var(--dashboard-table-line)_12%,transparent)] p-2">
      {tabs.map((tab) => (
        <button
          key={tab.id}
          type="button"
          onClick={() => onChange(tab.id)}
          className={cn(
            "inline-flex h-10 shrink-0 items-center gap-2 rounded-pill px-4 text-sm font-semibold transition",
            activeTab === tab.id
              ? "bg-[var(--login-submit-start)] text-white shadow-sm"
              : "text-panel-copy hover:bg-[color-mix(in_srgb,var(--dashboard-nav-hover)_72%,transparent)] hover:text-panel-strong",
          )}
        >
          {tab.icon}
          {tab.label}
        </button>
      ))}
    </div>
  );
}

function AttentionSummaryPanel({
  data,
  onReviewIssues,
  onReviewPhoneMenus,
}: {
  data: MessageGovernanceDashboardResponse;
  onReviewIssues: () => void;
  onReviewPhoneMenus: () => void;
}) {
  const attentionItems = data.missing_translation_dashboard.items;
  const attentionCount = attentionItems.length || data.summary.strict_localization_issue_count;
  const firstIssue = attentionItems[0];
  const hasPhoneMenuIssue = attentionItems.some((item) => item.issue_type.includes("ussd"));
  const title = attentionCount
    ? `${attentionCount} ${attentionCount === 1 ? "item needs" : "items need"} review before rollout`
    : "Messages are ready to use";
  const message = firstIssue
    ? humanIssueMessage(firstIssue.message, firstIssue.language)
    : "Approved messages are available in the supported languages. Keep watching sending results as teams use them.";

  return (
    <Card
      className={cn(
        "grid gap-4 p-5 lg:grid-cols-[1fr_auto]",
        attentionCount ? "border-[color-mix(in_srgb,var(--warning)_34%,var(--dashboard-table-line))]" : "",
      )}
      tone={attentionCount ? "attention" : "soft"}
    >
      <div className="flex gap-3">
        <span
          className={cn(
            "mt-1 inline-flex size-10 shrink-0 items-center justify-center rounded-2xl",
            attentionCount
              ? "bg-[color-mix(in_srgb,var(--warning)_16%,transparent)] text-[color:var(--warning)]"
              : "bg-[color-mix(in_srgb,var(--success)_16%,transparent)] text-[color:var(--success)]",
          )}
        >
          {attentionCount ? <AlertTriangle className="size-5" /> : <CheckCircle2 className="size-5" />}
        </span>
        <div>
          <p className="text-lg font-semibold text-panel-strong">{title}</p>
          <p className="mt-1 max-w-3xl text-sm leading-6 text-panel-muted">{message}</p>
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-2 lg:justify-end">
        {attentionCount ? (
          <Button type="button" onClick={hasPhoneMenuIssue ? onReviewPhoneMenus : onReviewIssues}>
            {hasPhoneMenuIssue ? "Review phone menus" : "Review items"}
            <ArrowRight className="size-4" />
          </Button>
        ) : null}
        <Button type="button" variant="secondary" onClick={onReviewIssues}>
          View details
        </Button>
      </div>
    </Card>
  );
}

export default function MessageGovernancePage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const filters = useMemo(() => paramsFromSearch(searchParams), [searchParams]);
  const { currentUser } = useAuth();
  const { data, isPending, error, refetch, isFetching } = useMessageGovernanceDashboardQuery(filters);
  const approveMutation = useApproveMessageTemplateMutation();
  const approveUssdMutation = useApproveUssdMenuVersionMutation();
  const [draftFilters, setDraftFilters] = useState(filters);
  const [selectedTemplateId, setSelectedTemplateId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<MessageReviewTab>("attention");
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const { data: selectedTemplateDetail } = useMessageTemplateDetailQuery(selectedTemplateId);

  const lastUpdatedLabel = data?.generated_at ? formatRelativeTimestamp(data.generated_at) : "No recent update";
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
  const sideBySidePreview = selectedTemplateDetail?.side_by_side_preview ?? previewRowsFromVariants(languageVariants);

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
      setActionMessage(`${statusLabel(action)} saved for ${selectedTemplate.title}.`);
      await refetch();
    } catch (approvalError) {
      setActionError(approvalError instanceof Error ? approvalError.message : "Unable to update message review.");
    }
  }

  async function handleUssdApprovalAction(
    publicId: string,
    title: string,
    action: UssdMenuVersionApprovalPayload["action"],
  ) {
    setActionError(null);
    setActionMessage(null);
    try {
      await approveUssdMutation.mutateAsync({
        publicId,
        payload: {
          action,
          reason: "Reviewed from the communication review page.",
        },
      });
      setActionMessage(`${statusLabel(action)} saved for ${title}.`);
      await refetch();
    } catch (approvalError) {
      setActionError(approvalError instanceof Error ? approvalError.message : "Unable to update phone menu review.");
    }
  }

  return (
    <RoleGate
      allowedRoles={MESSAGE_GOVERNANCE_ROLES}
      title="Communication review unavailable"
      message="Your role cannot view communication review."
    >
      <div className="space-y-8">
        <DashboardTopbar
          title="Communication Review"
          subtitle="Review the messages people receive and fix anything that needs attention."
          lastUpdatedLabel={lastUpdatedLabel}
          lastUpdatedTone={data?.summary.audit_status === "pass" ? "default" : "stale"}
          onRefresh={() => refetch()}
        />

        <PageSectionHeader
          title="Public Messages"
          description="Review SMS, phone menu, dashboard, and offline CHV messages in one calm workspace."
          actions={
            <Button type="button" variant="secondary" onClick={() => refetch()} disabled={isFetching}>
              <RefreshCcw className={cn("size-4", isFetching && "animate-spin")} />
              Refresh
            </Button>
          }
        />

        <form
          onSubmit={applyFilters}
          className="grid gap-3 rounded-panel border border-panel-table-wrap bg-[color-mix(in_srgb,var(--dashboard-table-line)_14%,transparent)] p-4 lg:grid-cols-[1.2fr_repeat(4,minmax(0,0.8fr))_auto]"
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
                <option key={audience} value={audience}>{audienceLabel(audience)}</option>
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
                <option key={channel} value={channel}>{channelLabel(channel)}</option>
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
                <option key={language} value={language}>{languageLabel(language)}</option>
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
                <option key={statusValue} value={statusValue}>{statusLabel(statusValue)}</option>
              ))}
            </select>
          </label>
          <div className="flex items-end gap-2">
            <Button type="submit">
              <Filter className="size-4" />
              Apply
            </Button>
            <Button type="button" variant="secondary" onClick={resetFilters}>
              Reset
            </Button>
          </div>
          <details className="lg:col-span-full">
            <summary className="cursor-pointer text-sm font-semibold text-panel-copy">More filters</summary>
            <div className="mt-3 grid max-w-lg grid-cols-2 gap-2">
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
          </details>
        </form>

        {error ? (
          <Card className="border-[color-mix(in_srgb,var(--danger)_28%,var(--dashboard-table-line))] p-5">
            <div className="flex items-start gap-3">
              <AlertTriangle className="mt-0.5 size-5 text-[color:var(--danger)]" />
              <div>
                <p className="font-semibold text-panel-strong">Unable to load communication review</p>
                <p className="mt-1 text-sm text-panel-muted">{error.message}</p>
              </div>
            </div>
          </Card>
        ) : null}

        {actionError ? (
          <Card className="border-[color-mix(in_srgb,var(--danger)_28%,var(--dashboard-table-line))] p-5">
            <p className="font-semibold text-panel-strong">Review update failed</p>
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
          <div className="space-y-6">
            <AttentionSummaryPanel
              data={data}
              onReviewIssues={() => setActiveTab("attention")}
              onReviewPhoneMenus={() => setActiveTab("phone")}
            />

            <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
              <SummaryTile
                icon={<CheckCircle2 className="size-5" />}
                label="Messages ready"
                value={`${data.summary.approved_template_count}/${data.summary.template_count}`}
                helper="Approved for use"
                tone="success"
              />
              <SummaryTile
                icon={<AlertTriangle className="size-5" />}
                label="Needs review"
                value={data.missing_translation_dashboard.items.length || data.summary.strict_localization_issue_count}
                helper={data.missing_translation_dashboard.items.length ? "Fix before rollout" : "No open language items"}
                tone={data.missing_translation_dashboard.items.length || data.summary.strict_localization_issue_count ? "warning" : "success"}
              />
              <SummaryTile
                icon={<Languages className="size-5" />}
                label="Languages ready"
                value={data.summary.language_count}
                helper={languageListLabel(data.summary.languages)}
                tone={data.summary.missing_translation_count ? "warning" : "success"}
              />
              <SummaryTile
                icon={<UsersRound className="size-5" />}
                label="People reached"
                value={data.summary.communication_reach_count}
                helper={`${formatPercent(data.summary.delivery_success_rate_pct)} sending success`}
              />
            </section>

            <ReviewTabs activeTab={activeTab} onChange={setActiveTab} />

            {activeTab === "attention" ? (
              <section className="grid gap-6 xl:grid-cols-[0.85fr_1.15fr]">
                <section className="grid content-start gap-4">
                  <SectionTitle icon={<AlertTriangle className="size-5" />} title="Needs Attention" />
                  <MissingTranslationDashboardPanel items={data.missing_translation_dashboard.items} />
                </section>
                <LocalizationRolloutPanel
                  rollout={data.audit.localization_rollout}
                  strictIssueCount={data.audit.strict_localization_issue_count}
                />
              </section>
            ) : null}

            {activeTab === "messages" ? (
              <section className="grid gap-6 xl:grid-cols-[1.05fr_0.95fr]">
                <section className="grid content-start gap-4">
                  <SectionTitle icon={<MessageSquareText className="size-5" />} title="Messages" />
                  <TemplateList
                    templates={data.templates}
                    selectedPublicId={selectedTemplateId}
                    onSelect={(template) => setSelectedTemplateId(template.public_id)}
                  />
                </section>

                <section className="grid content-start gap-4">
                  <SectionTitle icon={<Eye className="size-5" />} title="Message Preview" />
                  <TemplateDetailPanel
                    template={selectedTemplate}
                    versionHistory={versionHistory}
                    languageVariants={languageVariants}
                    sideBySidePreview={sideBySidePreview}
                    canApprove={canApprove}
                    onApprovalAction={handleApprovalAction}
                    isUpdating={approveMutation.isPending}
                  />
                </section>
              </section>
            ) : null}

            {activeTab === "languages" ? (
              <section className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
                <section className="grid content-start gap-4">
                  <SectionTitle icon={<Languages className="size-5" />} title="Language Readiness" />
                  <LanguageCoverageMatrix rows={data.template_language_coverage.rows} />
                </section>
                <section className="grid content-start gap-4">
                  <SectionTitle icon={<ClipboardCheck className="size-5" />} title="CHV Guide Preview" />
                  <OfflineGuidancePreview previews={data.offline_guidance_preview} />
                </section>
              </section>
            ) : null}

            {activeTab === "sending" ? (
              <div className="space-y-6">
                <section className="grid gap-6 xl:grid-cols-2">
                  <section className="grid content-start gap-4">
                    <SectionTitle icon={<UsersRound className="size-5" />} title="Reach" />
                    <CommunicationReachTable rows={data.delivery_summary.reach_by_audience_channel} />
                  </section>

                  <section className="grid content-start gap-4">
                    <SectionTitle icon={<Ban className="size-5" />} title="Stopped Messages" />
                    <OptOutMonitoringTable rows={data.delivery_summary.opt_out_summary.by_audience_channel} />
                  </section>
                </section>

                <section className="grid gap-6 xl:grid-cols-[0.95fr_1.05fr]">
                  <section className="grid content-start gap-4">
                    <SectionTitle icon={<Send className="size-5" />} title="Sending Results" />
                    <DeliveryOutcomeTable rows={data.delivery_summary.by_audience_channel_status} />
                  </section>

                  <section className="grid content-start gap-4">
                    <SectionTitle icon={<Smartphone className="size-5" />} title="Phone Menu Use" />
                    <div className="grid gap-3 md:grid-cols-3">
                      <SummaryTile icon={<CheckCircle2 className="size-5" />} label="Completed" value={data.ussd_analytics.completed_sessions} tone="success" />
                      <SummaryTile icon={<AlertTriangle className="size-5" />} label="Unclear choices" value={data.ussd_analytics.invalid_input_sessions} tone="warning" />
                      <SummaryTile icon={<History className="size-5" />} label="Left early" value={data.ussd_analytics.abandoned_sessions} tone="danger" />
                    </div>
                    <div className="overflow-hidden rounded-panel border border-panel-table-wrap bg-panel">
                      {data.ussd_analytics.by_menu_version.slice(0, 8).map((row) => (
                        <div key={`${row.menu_key}-${row.menu_version_label}-${row.language}`} className="grid grid-cols-[1fr_0.6fr_0.6fr_0.6fr] gap-3 border-b border-[var(--dashboard-table-line)] px-4 py-3 text-sm last:border-b-0 max-[760px]:grid-cols-2">
                          <span className="font-semibold text-panel-strong">{row.menu_version_label}</span>
                          <span>{languageLabel(row.language)}</span>
                          <span>{row.session_count} sessions</span>
                          <span>{row.invalid_input_count} unclear</span>
                        </div>
                      ))}
                    </div>
                  </section>
                </section>

                <section className="grid gap-4">
                  <SectionTitle icon={<History className="size-5" />} title="Message Use" />
                  <TemplateUsageTable rows={data.delivery_summary.template_usage_by_version} />
                </section>
              </div>
            ) : null}

            {activeTab === "phone" ? (
              <div className="space-y-6">
                <section className="grid gap-4">
                  <SectionTitle icon={<Smartphone className="size-5" />} title="Phone Menu Preview" />
                  <UssdRouteTreePreview previews={data.ussd_route_tree_preview} />
                </section>

                <section className="grid gap-4">
                  <SectionTitle icon={<Languages className="size-5" />} title="Phone Menu Updates" />
                  <UssdMenuVersionList
                    menuVersions={data.ussd_menu_versions}
                    canApprove={canApprove}
                    isUpdating={approveUssdMutation.isPending}
                    onApprovalAction={handleUssdApprovalAction}
                  />
                </section>
              </div>
            ) : null}
          </div>
        ) : null}
      </div>
    </RoleGate>
  );
}
