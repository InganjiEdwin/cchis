import * as React from "react";

import { cn } from "@/lib/cn";

type StatusBannerTone = "default" | "success" | "warning" | "danger" | "info";

const toneClasses: Record<StatusBannerTone, string> = {
  default:
    "border-panel-table-wrap bg-[color-mix(in_srgb,var(--dashboard-table-line)_26%,var(--dashboard-panel-surface))] text-panel-copy",
  success:
    "border-[color-mix(in_srgb,var(--success)_28%,var(--dashboard-panel-border))] bg-[color-mix(in_srgb,var(--success)_10%,var(--dashboard-panel-surface))] text-[color:var(--success)]",
  warning:
    "border-[color-mix(in_srgb,var(--warning)_30%,var(--dashboard-panel-border))] bg-[color-mix(in_srgb,var(--warning)_11%,var(--dashboard-panel-surface))] text-[color:var(--warning)]",
  danger:
    "border-[color-mix(in_srgb,var(--danger)_30%,var(--dashboard-panel-border))] bg-[color-mix(in_srgb,var(--danger)_10%,var(--dashboard-panel-surface))] text-[color:var(--danger)]",
  info:
    "border-[color-mix(in_srgb,var(--brand)_26%,var(--dashboard-panel-border))] bg-[color-mix(in_srgb,var(--brand)_10%,var(--dashboard-panel-surface))] text-brand",
};

type StatusBannerProps = React.HTMLAttributes<HTMLDivElement> & {
  tone?: StatusBannerTone;
  icon?: React.ReactNode;
};

export function StatusBanner({ className, tone = "default", icon, children, ...props }: StatusBannerProps) {
  return (
    <div
      className={cn(
        "flex items-start gap-3 rounded-2xl border px-4 py-3 text-sm font-medium",
        toneClasses[tone],
        className,
      )}
      {...props}
    >
      {icon ? <span className="mt-0.5 shrink-0 [&_svg]:size-4">{icon}</span> : null}
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  );
}
