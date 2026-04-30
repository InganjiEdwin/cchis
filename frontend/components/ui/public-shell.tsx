"use client";

import { ArrowLeft, Moon, Sun } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import type { ReactNode } from "react";
import { useEffect, useState } from "react";

import { cn } from "@/lib/cn";
import { applyThemePreference, persistThemePreference } from "@/lib/theme-preference";

export function PublicScreen({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "min-h-screen bg-[var(--login-background)] text-[var(--login-ink)] dark:bg-[var(--totp-background)] dark:text-[var(--totp-ink)]",
        className,
      )}
    >
      {children}
    </div>
  );
}

export function PublicGlow({ side }: { side: "left" | "right" }) {
  return (
    <div
      aria-hidden="true"
      className={cn(
        "pointer-events-none fixed inset-y-0 w-80 blur-3xl",
        side === "left"
          ? "left-[-6rem] bg-[var(--login-glow-left)]"
          : "right-[-6rem] bg-[var(--login-glow-right)]",
      )}
    />
  );
}

export function PublicTopbar({
  backHref = "/login",
  backLabel = "Back to Login",
  brand = "CHIS",
  brandHref = "/login",
  showHelp = false,
  extra,
}: {
  backHref?: string;
  backLabel?: string;
  brand?: string;
  brandHref?: string;
  showHelp?: boolean;
  extra?: ReactNode;
}) {
  const [effectiveTheme, setEffectiveTheme] = useState<"LIGHT" | "DARK">("LIGHT");

  useEffect(() => {
    if (typeof document === "undefined") {
      return;
    }

    const themeAttribute = document.documentElement.getAttribute("data-theme");
    setEffectiveTheme(themeAttribute === "dark" ? "DARK" : "LIGHT");
  }, []);

  function handleThemeToggle() {
    const nextTheme = effectiveTheme === "DARK" ? "LIGHT" : "DARK";
    setEffectiveTheme(nextTheme);
    applyThemePreference(nextTheme);
    persistThemePreference(nextTheme);
  }

  const themeToggleLabel = effectiveTheme === "DARK" ? "Switch to light mode" : "Switch to dark mode";
  const ThemeToggleIcon = effectiveTheme === "DARK" ? Sun : Moon;

  return (
    <header className="flex items-center justify-between border-b border-[var(--forgot-topbar-line)] bg-[var(--forgot-topbar-surface)] px-5 py-4 backdrop-blur md:px-8">
      <Link href={brandHref} className="inline-flex items-center gap-2.5 text-lg font-semibold tracking-tight text-[var(--forgot-brand)]">
        <Image
          src="/brand/chis-brief-colored.png"
          alt=""
          width={28}
          height={28}
          className="size-7 rounded-xl"
        />
        <span>{brand}</span>
      </Link>
      <div className="flex items-center gap-3">
        {extra}
        <button
          type="button"
          onClick={handleThemeToggle}
          aria-label={themeToggleLabel}
          title={themeToggleLabel}
          className="inline-flex size-10 items-center justify-center rounded-full border border-[var(--forgot-topbar-line)] bg-[color:var(--forgot-help-surface)] text-[var(--forgot-help-ink)] transition hover:text-[var(--forgot-link-hover)]"
        >
          <ThemeToggleIcon className="size-4" aria-hidden="true" />
        </button>
        <Link href={backHref} className="text-sm font-medium text-[var(--forgot-link)] transition hover:text-[var(--forgot-link-hover)]">
          {backLabel}
        </Link>
        {showHelp ? (
          <span className="inline-flex size-9 items-center justify-center rounded-full bg-[var(--forgot-help-surface)] text-[var(--forgot-help-ink)]">
            ?
          </span>
        ) : null}
      </div>
    </header>
  );
}

export function PublicShell({
  children,
  narrow = false,
  className,
}: {
  children: ReactNode;
  narrow?: boolean;
  className?: string;
}) {
  return (
    <main
      className={cn(
        "mx-auto flex min-h-screen w-full flex-col items-center justify-center px-4 py-5 md:px-6 md:py-6",
        narrow ? "max-w-3xl" : "max-w-6xl",
        className,
      )}
    >
      {children}
    </main>
  );
}

export function PublicCard({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      className={cn(
        "w-full rounded-[2rem] border border-[var(--forgot-card-border)] bg-[var(--forgot-card-surface)] p-6 shadow-[var(--forgot-card-shadow)] backdrop-blur md:p-8",
        className,
      )}
    >
      {children}
    </section>
  );
}

export function PublicFooter() {
  return (
    <footer className="mt-5 flex flex-col items-center gap-2 text-center text-xs text-[var(--login-footer-ink)] md:mt-6">
      <p>&copy; 2026 Climate Health Intelligence System. All rights reserved.</p>
      <div className="flex items-center gap-3">
        <Link href="/privacy" className="transition hover:text-[var(--login-link-hover)]">
          Privacy Policy
        </Link>
        <Link href="/terms" className="transition hover:text-[var(--login-link-hover)]">
          Terms of Service
        </Link>
      </div>
    </footer>
  );
}

export function BrandLockup({
  image = false,
  title = "CCHIS",
  subtitle,
}: {
  image?: boolean;
  title?: string;
  subtitle?: string;
}) {
  return (
    <div className="mb-5 flex flex-col items-center gap-2.5 text-center md:mb-6 md:gap-3">
      {image ? (
        <div className="w-full max-w-[320px] md:max-w-[360px]">
          <Image
            src="/brand/chis-full-colored.png"
            alt="Climate Health Intelligence System"
            width={864}
            height={236}
            priority
            className="h-auto w-full"
          />
        </div>
      ) : (
        <div className="flex items-center gap-2.5">
          <span className="inline-flex size-10 items-center justify-center rounded-2xl bg-[var(--totp-brand-mark-surface)] text-white shadow-[var(--totp-brand-mark-shadow)]">
            <span className="text-base font-bold">C</span>
          </span>
          <span className="text-2xl font-semibold tracking-tight text-[var(--totp-brand-ink)]">{title}</span>
        </div>
      )}
      {subtitle ? (
        <p className={cn("max-w-lg text-sm leading-snug text-[var(--login-description)]", image ? "pt-4 md:pt-5" : "")}>
          {subtitle}
        </p>
      ) : null}
    </div>
  );
}

export function SectionBackLink({
  href = "/login",
  label = "Back to Login",
}: {
  href?: string;
  label?: string;
}) {
  return (
    <Link href={href} className="inline-flex items-center gap-2 text-sm font-medium text-[var(--login-link)] transition hover:text-[var(--login-link-hover)]">
      <ArrowLeft className="size-4" aria-hidden="true" />
      {label}
    </Link>
  );
}

export function PublicAlert({
  tone = "default",
  children,
}: {
  tone?: "default" | "error" | "success" | "warning";
  children: ReactNode;
}) {
  const toneClasses =
    tone === "error"
      ? "border-[var(--login-error-border)] bg-[var(--login-error-surface)] text-[var(--login-error-ink)]"
      : tone === "success"
        ? "border-[var(--forgot-success-border)] bg-[var(--forgot-success-surface)] text-[var(--forgot-success-ink)]"
        : tone === "warning"
          ? "border-[color-mix(in_srgb,var(--warning)_28%,white)] bg-[color-mix(in_srgb,var(--warning)_10%,white)] text-[color:var(--warning)]"
          : "border-[var(--request-support-border)] bg-[var(--request-support-surface)] text-[var(--request-support-heading)]";

  return <div className={cn("rounded-2xl border px-4 py-3 text-sm", toneClasses)}>{children}</div>;
}
