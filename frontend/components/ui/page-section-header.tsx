import * as React from "react";

import { cn } from "@/lib/cn";

type PageSectionHeaderProps = React.HTMLAttributes<HTMLDivElement> & {
  title: string;
  description?: string;
  actions?: React.ReactNode;
};

export function PageSectionHeader({
  className,
  title,
  description,
  actions,
  ...props
}: PageSectionHeaderProps) {
  return (
    <div className={cn("flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between", className)} {...props}>
      <div className="min-w-0">
        <h2 className="text-[clamp(1.5rem,1rem+1vw,2rem)] font-semibold leading-tight text-panel-strong">{title}</h2>
        {description ? <p className="mt-1 max-w-3xl text-sm text-panel-muted">{description}</p> : null}
      </div>
      {actions ? <div className="flex shrink-0 items-center gap-3">{actions}</div> : null}
    </div>
  );
}
