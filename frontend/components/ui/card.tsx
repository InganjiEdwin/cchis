import * as React from "react";

import { cn } from "@/lib/cn";

type CardProps = React.HTMLAttributes<HTMLDivElement> & {
  tone?: "default" | "soft" | "attention";
};

const toneClasses: Record<NonNullable<CardProps["tone"]>, string> = {
  default: "border-panel-border bg-panel shadow-panel",
  soft: "border-panel-table-wrap bg-[var(--dashboard-attention-card-surface)] shadow-[var(--dashboard-attention-card-primary-shadow)]",
  attention: "border-panel-table-wrap bg-[var(--dashboard-attention-card-primary-surface)] shadow-[var(--dashboard-attention-card-primary-shadow)]",
};

export function Card({ className, tone = "default", ...props }: CardProps) {
  return <div className={cn("rounded-panel border text-panel-copy", toneClasses[tone], className)} {...props} />;
}
