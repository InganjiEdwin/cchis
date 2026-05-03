"use client";

import { CheckCircle2, Circle } from "lucide-react";

import { cn } from "@/lib/cn";
import { getPasswordPolicyRequirements } from "@/lib/password-policy";

type PasswordPolicyChecklistProps = {
  password: string;
  className?: string;
};

export function PasswordPolicyChecklist({ password, className }: PasswordPolicyChecklistProps) {
  const requirements = getPasswordPolicyRequirements(password);

  return (
    <ul
      aria-label="Password requirements"
      className={cn(
        "grid gap-2 rounded-[1rem] border border-panel-table-wrap bg-[color-mix(in_srgb,var(--dashboard-icon-button-surface)_72%,transparent)] p-3 text-xs font-semibold sm:grid-cols-2",
        className,
      )}
    >
      {requirements.map((requirement) => {
        const Icon = requirement.isMet ? CheckCircle2 : Circle;

        return (
          <li
            key={requirement.id}
            className={cn(
              "flex min-w-0 items-center gap-2",
              requirement.isMet ? "text-emerald-300" : "text-panel-muted",
            )}
          >
            <Icon className="size-4 shrink-0" aria-hidden="true" />
            <span className="min-w-0">{requirement.label}</span>
          </li>
        );
      })}
    </ul>
  );
}
