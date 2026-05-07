"use client";

import { ChevronDown } from "lucide-react";
import { useId, useState, type ReactNode } from "react";

import { Card } from "@/components/ui/card";
import { StatusBadge } from "@/components/ui/status-badge";
import { cn } from "@/lib/cn";
import type { WardOperationalEvidenceTone } from "@/lib/dashboard";

export type WardDetailTabId = "situation" | "response" | "evidence" | "history";
export type WardDisclosureTone = "default" | "success" | "warning" | "danger";

export type WardHeaderMetric = {
  label: string;
  value: ReactNode;
};

type WardShellProps = {
  children: ReactNode;
  className?: string;
};

export function WardCockpitHeader({ children, className }: WardShellProps) {
  return (
    <Card className={cn("space-y-5 overflow-hidden rounded-lg p-4 md:space-y-6 md:p-8", className)}>
      {children}
    </Card>
  );
}

export function WardActionRail({ children, className }: WardShellProps) {
  return <aside className={cn("space-y-6 xl:sticky xl:top-24 xl:self-start", className)}>{children}</aside>;
}

type WardTrustSummaryItem = {
  id: string;
  label: string;
  value: string;
  tone?: WardOperationalEvidenceTone;
};

type WardTrustSummaryProps = {
  items: WardTrustSummaryItem[];
  className?: string;
};

function trustToneToBadgeTone(tone: WardOperationalEvidenceTone | undefined) {
  if (tone === "danger") return "danger" as const;
  if (tone === "warning") return "warning" as const;
  if (tone === "success") return "success" as const;
  return "default" as const;
}

export function WardTrustSummary({ items, className }: WardTrustSummaryProps) {
  if (items.length === 0) {
    return null;
  }

  return (
    <div className={cn("flex flex-wrap gap-2", className)}>
      {items.map((item) => (
        <StatusBadge
          key={item.id}
          tone={trustToneToBadgeTone(item.tone)}
          className="max-w-full whitespace-normal rounded-full px-3 py-2 text-center leading-4 tracking-[0.14em]"
        >
          {item.label}: {item.value}
        </StatusBadge>
      ))}
    </div>
  );
}

type WardDetailTabsProps = {
  activeTab: WardDetailTabId;
  tabs: Array<{
    id: WardDetailTabId;
    label: string;
  }>;
  onSelectTab?: (tabId: WardDetailTabId) => void;
  className?: string;
};

export function WardDetailTabs({ activeTab, tabs, onSelectTab, className }: WardDetailTabsProps) {
  return (
    <div className={cn("flex flex-wrap gap-2", className)} role="tablist" aria-label="Ward detail sections">
      {tabs.map((tab) => (
        <button
          key={tab.id}
          type="button"
          role="tab"
          aria-selected={activeTab === tab.id}
          className={cn(
            "min-h-10 rounded-pill border px-4 py-2 text-sm font-semibold leading-5 transition",
            activeTab === tab.id
              ? "border-[var(--brand)] bg-[color-mix(in_srgb,var(--brand)_10%,white)] text-brand"
              : "border-[var(--dashboard-table-line)] bg-[color-mix(in_srgb,var(--dashboard-table-line)_16%,transparent)] text-panel-copy hover:bg-[color-mix(in_srgb,var(--dashboard-table-line)_30%,transparent)]",
          )}
          onClick={() => onSelectTab?.(tab.id)}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}

type WardMetricStripProps = {
  metrics: WardHeaderMetric[];
  className?: string;
};

export function WardMetricStrip({ metrics, className }: WardMetricStripProps) {
  return (
    <div className={cn("grid gap-4 md:grid-cols-2 xl:grid-cols-4", className)}>
      {metrics.map((metric) => (
        <div
          key={metric.label}
          className="min-w-0 rounded-lg border border-[var(--dashboard-table-line)] bg-[color-mix(in_srgb,var(--dashboard-table-line)_20%,transparent)] p-4"
        >
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-panel-muted">{metric.label}</p>
          <p className="mt-2 break-words text-lg font-semibold leading-6 text-panel-strong">{metric.value}</p>
        </div>
      ))}
    </div>
  );
}

type WardDetailDisclosureProps = {
  title: string;
  summary?: ReactNode;
  badge?: ReactNode;
  badgeTone?: WardDisclosureTone;
  children: ReactNode;
  defaultOpen?: boolean;
  className?: string;
  bodyClassName?: string;
};

function disclosureToneClasses(tone: WardDisclosureTone | undefined) {
  if (tone === "danger") {
    return "border-[color-mix(in_srgb,var(--danger)_28%,var(--dashboard-table-line))] bg-[color-mix(in_srgb,var(--danger)_7%,var(--panel))]";
  }
  if (tone === "warning") {
    return "border-[color-mix(in_srgb,var(--warning)_24%,var(--dashboard-table-line))] bg-[color-mix(in_srgb,var(--warning)_7%,var(--panel))]";
  }
  if (tone === "success") {
    return "border-[color-mix(in_srgb,var(--success)_22%,var(--dashboard-table-line))] bg-[color-mix(in_srgb,var(--success)_6%,var(--panel))]";
  }
  return "border-[var(--dashboard-table-line)] bg-[color-mix(in_srgb,var(--dashboard-table-line)_14%,transparent)]";
}

export function WardDetailDisclosure({
  title,
  summary,
  badge,
  badgeTone = "default",
  children,
  defaultOpen = false,
  className,
  bodyClassName,
}: WardDetailDisclosureProps) {
  const [isOpen, setIsOpen] = useState(defaultOpen);
  const contentId = useId();

  return (
    <div className={cn("overflow-hidden rounded-lg border", disclosureToneClasses(badgeTone), className)}>
      <button
        type="button"
        aria-expanded={isOpen}
        aria-controls={contentId}
        className="flex w-full flex-col gap-4 px-4 py-4 text-left transition hover:bg-[color-mix(in_srgb,var(--dashboard-table-line)_12%,transparent)] sm:flex-row sm:items-start sm:justify-between"
        onClick={() => setIsOpen((current) => !current)}
      >
        <span className="min-w-0 space-y-1">
          <span className="block text-sm font-semibold text-panel-strong">{title}</span>
          {summary ? <span className="block text-sm leading-6 text-panel-muted">{summary}</span> : null}
        </span>
        <span className="flex max-w-full flex-wrap items-center gap-2 sm:shrink-0 sm:justify-end">
          {badge ? (
            <StatusBadge tone={badgeTone} className="max-w-full whitespace-normal rounded-full px-3 py-2 text-center leading-4 tracking-[0.14em]">
              {badge}
            </StatusBadge>
          ) : null}
          <ChevronDown className={cn("size-4 text-panel-muted transition", isOpen && "rotate-180")} aria-hidden="true" />
        </span>
      </button>
      {isOpen ? (
        <div id={contentId} className={cn("border-t border-[var(--dashboard-table-line)] px-4 py-4", bodyClassName)}>
          {children}
        </div>
      ) : null}
    </div>
  );
}

type LoadingBlocksProps = {
  count?: number;
  className?: string;
};

export function LoadingBlocks({
  count = 3,
  className = "h-16 rounded-lg bg-[color-mix(in_srgb,var(--dashboard-table-line)_55%,transparent)]",
}: LoadingBlocksProps) {
  return (
    <div className="space-y-4" aria-hidden="true">
      {Array.from({ length: count }, (_, index) => (
        <div key={index} className={className} />
      ))}
    </div>
  );
}
