import * as React from "react";

import { cn } from "@/lib/cn";

type StatusBadgeTone = "default" | "success" | "warning" | "danger" | "info";

const toneClasses: Record<StatusBadgeTone, string> = {
  default: "bg-[color-mix(in_srgb,var(--dashboard-table-line)_70%,transparent)] text-panel-copy",
  success: "bg-[color-mix(in_srgb,var(--success)_16%,white)] text-[color:var(--success)] dark:bg-[color-mix(in_srgb,var(--success)_24%,transparent)]",
  warning: "bg-[color-mix(in_srgb,var(--warning)_14%,white)] text-[color:var(--warning)] dark:bg-[color-mix(in_srgb,var(--warning)_22%,transparent)]",
  danger: "bg-[color-mix(in_srgb,var(--danger)_14%,white)] text-[color:var(--danger)] dark:bg-[color-mix(in_srgb,var(--danger)_22%,transparent)]",
  info: "bg-[color-mix(in_srgb,var(--dashboard-sidebar-title)_12%,white)] text-brand dark:bg-[color-mix(in_srgb,var(--dashboard-sidebar-title)_20%,transparent)]",
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
