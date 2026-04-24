"use client";

import * as React from "react";

import { cn } from "@/lib/cn";

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
type ButtonSize = "sm" | "md" | "lg" | "icon";

export type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  size?: ButtonSize;
};

const variantClasses: Record<ButtonVariant, string> = {
  primary:
    "bg-[var(--login-submit-start)] text-white shadow-[var(--login-submit-shadow)] hover:bg-[var(--login-submit-end)] hover:shadow-[var(--login-submit-shadow-hover)]",
  secondary:
    "border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] text-panel-copy hover:border-[var(--dashboard-icon-button-border)] hover:text-[var(--dashboard-icon-button-ink-hover)]",
  ghost:
    "bg-transparent text-panel-copy hover:bg-[color-mix(in_srgb,var(--dashboard-nav-hover)_72%,transparent)] hover:text-panel-strong",
  danger:
    "bg-[color:var(--danger)] text-white shadow-sm hover:opacity-95",
};

const sizeClasses: Record<ButtonSize, string> = {
  sm: "h-9 rounded-pill px-3 text-sm font-medium",
  md: "h-11 rounded-pill px-4 text-sm font-semibold",
  lg: "h-12 rounded-pill px-5 text-base font-semibold",
  icon: "size-11 rounded-pill p-0",
};

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { className, variant = "primary", size = "md", type = "button", ...props },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      className={cn(
        "inline-flex appearance-none items-center justify-center gap-2 whitespace-nowrap border-0 outline-none ring-0 transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand/30 disabled:pointer-events-none disabled:opacity-60",
        variantClasses[variant],
        sizeClasses[size],
        className,
      )}
      {...props}
    />
  );
});
