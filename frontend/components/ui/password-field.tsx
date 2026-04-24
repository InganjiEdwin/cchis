"use client";

import { Eye, EyeOff, LockKeyhole } from "lucide-react";
import { useState } from "react";

import { cn } from "@/lib/cn";

type PasswordFieldProps = {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  autoComplete?: string;
  className?: string;
};

export function PasswordField({
  id,
  label,
  value,
  onChange,
  placeholder,
  autoComplete,
  className,
}: PasswordFieldProps) {
  const [visible, setVisible] = useState(false);

  return (
    <label className={cn("flex min-w-0 flex-col gap-1.5", className)}>
      <span className="text-sm font-medium text-panel-copy">{label}</span>
      <span className="flex h-10 items-center gap-3 rounded-pill border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] px-4 text-panel-copy shadow-sm transition focus-within:border-[var(--dashboard-icon-button-border)]">
        <LockKeyhole className="size-4 shrink-0 text-panel-muted" aria-hidden="true" />
        <input
          id={id}
          name={id}
          type={visible ? "text" : "password"}
          autoComplete={autoComplete}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder={placeholder}
          className="min-w-0 flex-1 appearance-none border-0 bg-transparent p-0 text-sm text-panel-strong outline-none ring-0 shadow-none placeholder:text-panel-subtle focus:border-0 focus:outline-none focus:ring-0"
          required
        />
        <button
          type="button"
          className="shrink-0 appearance-none border-0 bg-transparent p-0 text-panel-muted outline-none ring-0 transition hover:text-panel-strong focus:outline-none focus:ring-0"
          onClick={() => setVisible((current) => !current)}
          aria-label={visible ? "Hide password" : "Show password"}
        >
          {visible ? <EyeOff className="size-4" aria-hidden="true" /> : <Eye className="size-4" aria-hidden="true" />}
        </button>
      </span>
    </label>
  );
}
