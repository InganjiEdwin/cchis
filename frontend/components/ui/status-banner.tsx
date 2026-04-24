import * as React from "react";

import { cn } from "@/lib/cn";

type StatusBannerTone = "default" | "success" | "warning" | "danger" | "info";

const toneClasses: Record<StatusBannerTone, string> = {
  default:
    "border-panel-table-wrap bg-[color-mix(in_srgb,var(--dashboard-table-line)_32%,white)] text-panel-copy dark:bg-[color-mix(in_srgb,var(--dashboard-table-line)_72%,transparent)]",
  success:
    "border-[color-mix(in_srgb,var(--success)_20%,white)] bg-[color-mix(in_srgb,var(--success)_10%,white)] text-[color:var(--success)] dark:border-[color-mix(in_srgb,var(--success)_32%,transparent)] dark:bg-[color-mix(in_srgb,var(--success)_18%,transparent)]",
  warning:
    "border-[color-mix(in_srgb,var(--warning)_20%,white)] bg-[color-mix(in_srgb,var(--warning)_10%,white)] text-[color:var(--warning)] dark:border-[color-mix(in_srgb,var(--warning)_34%,transparent)] dark:bg-[color-mix(in_srgb,var(--warning)_18%,transparent)]",
  danger:
    "border-[color-mix(in_srgb,var(--danger)_20%,white)] bg-[color-mix(in_srgb,var(--danger)_10%,white)] text-[color:var(--danger)] dark:border-[color-mix(in_srgb,var(--danger)_34%,transparent)] dark:bg-[color-mix(in_srgb,var(--danger)_18%,transparent)]",
  info:
    "border-[color-mix(in_srgb,var(--brand)_14%,white)] bg-[color-mix(in_srgb,var(--brand)_8%,white)] text-brand dark:border-[color-mix(in_srgb,var(--brand)_28%,transparent)] dark:bg-[color-mix(in_srgb,var(--brand)_16%,transparent)]",
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
