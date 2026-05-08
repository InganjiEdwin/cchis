import * as React from "react";

import { cn } from "@/lib/cn";

type StatusBadgeTone = "default" | "success" | "warning" | "danger" | "info";

const toneClasses: Record<StatusBadgeTone, string> = {
  default: "bg-[color-mix(in_srgb,var(--dashboard-table-line)_70%,transparent)] text-panel-copy",
  success: "bg-[color-mix(in_srgb,var(--success)_18%,var(--dashboard-panel-surface))] text-[color:var(--success)]",
  warning: "bg-[color-mix(in_srgb,var(--warning)_16%,var(--dashboard-panel-surface))] text-[color:var(--warning)]",
  danger: "bg-[color-mix(in_srgb,var(--danger)_16%,var(--dashboard-panel-surface))] text-[color:var(--danger)]",
  info: "bg-[color-mix(in_srgb,var(--dashboard-sidebar-title)_14%,var(--dashboard-panel-surface))] text-brand",
};

type StatusBadgeProps = React.HTMLAttributes<HTMLSpanElement> & {
  tone?: StatusBadgeTone;
};

export function StatusBadge({ className, tone = "default", ...props }: StatusBadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-pill px-2.5 py-1 text-xs font-semibold uppercase tracking-[0.16em]",
        toneClasses[tone],
        className,
      )}
      {...props}
    />
  );
}
