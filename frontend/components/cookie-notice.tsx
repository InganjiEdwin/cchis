"use client";

import { ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";

const DEFAULT_COOKIE_NOTICE_VERSION = "cookies-2026-05";

export function getCookieNoticeStorageKey(version = DEFAULT_COOKIE_NOTICE_VERSION) {
  const normalizedVersion = version.trim() || DEFAULT_COOKIE_NOTICE_VERSION;
  return `cchis.cookie_notice_ack.${normalizedVersion}`;
}

export function CookieNotice({ version = DEFAULT_COOKIE_NOTICE_VERSION }: { version?: string }) {
  const storageKey = useMemo(() => getCookieNoticeStorageKey(version), [version]);
  const [isHydrated, setIsHydrated] = useState(false);
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    setIsHydrated(true);

    try {
      setIsVisible(window.localStorage.getItem(storageKey) !== "true");
    } catch {
      setIsVisible(true);
    }
  }, [storageKey]);

  function handleDismiss() {
    try {
      window.localStorage.setItem(storageKey, "true");
    } catch {
      // Keep the notice dismissible even when browser storage is unavailable.
    }

    setIsVisible(false);
  }

  if (!isHydrated || !isVisible) {
    return null;
  }

  return (
    <div className="pointer-events-none fixed bottom-4 left-4 right-4 z-[60] sm:left-auto sm:right-6 sm:max-w-xl" role="region" aria-label="Cookie notice">
      <div className="pointer-events-auto flex flex-col gap-3 rounded-lg border border-panel-table-wrap bg-[var(--forgot-card-surface)] p-4 text-panel-copy shadow-[var(--forgot-card-shadow)] backdrop-blur sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 items-start gap-3">
          <span className="mt-0.5 inline-flex size-9 shrink-0 items-center justify-center rounded-full bg-[color-mix(in_srgb,var(--dashboard-sidebar-title)_14%,white)] text-brand">
            <ShieldCheck className="size-4" aria-hidden="true" />
          </span>
          <p className="text-sm leading-6">
            CHIS uses essential cookies and storage to keep you signed in, remember your theme, and protect your account. We do not use advertising cookies.
          </p>
        </div>

        <div className="flex shrink-0 flex-wrap items-center gap-2 pl-12 sm:pl-0">
          <Link href="/privacy#cookies" className="inline-flex h-10 items-center px-2 text-sm font-semibold text-[var(--login-link)] transition hover:text-[var(--login-link-hover)]">
            Privacy Policy
          </Link>
          <Button type="button" size="sm" onClick={handleDismiss}>
            Got it
          </Button>
        </div>
      </div>
    </div>
  );
}
