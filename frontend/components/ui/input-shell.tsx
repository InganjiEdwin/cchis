import * as React from "react";

import { cn } from "@/lib/cn";

type InputShellProps = {
  label?: string;
  icon?: React.ReactNode;
  inputClassName?: string;
} & React.InputHTMLAttributes<HTMLInputElement>;

export const InputShell = React.forwardRef<HTMLInputElement, InputShellProps>(function InputShell(
  { className, inputClassName, label, icon, ...props },
  ref,
) {
  return (
    <label className={cn("flex min-w-0 flex-col gap-1.5", className)}>
      {label ? <span className="text-sm font-medium text-panel-copy">{label}</span> : null}
      <span className="flex h-10 items-center gap-3 rounded-pill border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] px-4 text-panel-copy shadow-sm transition focus-within:border-[var(--dashboard-icon-button-border)]">
        {icon ? <span className="shrink-0 text-panel-muted">{icon}</span> : null}
        <input
          ref={ref}
          className={cn(
            "min-w-0 flex-1 appearance-none border-0 bg-transparent p-0 text-sm text-panel-strong outline-none ring-0 shadow-none placeholder:text-panel-subtle focus:border-0 focus:outline-none focus:ring-0",
            inputClassName,
          )}
          {...props}
        />
      </span>
    </label>
  );
});
