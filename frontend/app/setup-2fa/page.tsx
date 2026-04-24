"use client";

import { ArrowLeft, KeyRound, Shield, ShieldAlert, Smartphone } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import { QRCodeSVG } from "qrcode.react";

import { useAuth } from "@/components/auth-provider";
import { Button } from "@/components/ui/button";
import {
  PublicAlert,
  PublicFooter,
  PublicScreen,
  PublicShell,
} from "@/components/ui/public-shell";
import { getDefaultRoute } from "@/lib/navigation";
import { isDashboardRole } from "@/lib/roles";

type SetupState = {
  manual_entry_key: string;
  provisioning_uri: string;
  account_name: string;
  issuer: string;
  two_factor_policy: "REQUIRED" | "OPTIONAL" | "NONE";
  is_totp_enabled: boolean;
};

export default function SetupTwoFactorPage() {
  const router = useRouter();
  const {
    beginTwoFactorEnrollment,
    clearPendingEnrollment,
    confirmTwoFactorEnrollment,
    currentUser,
    isAuthenticated,
    isHydrating,
    pendingEnrollment,
  } = useAuth();
  const [setup, setSetup] = useState<SetupState | null>(null);
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isLoadingSetup, setIsLoadingSetup] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [showManualSetup, setShowManualSetup] = useState(false);

  useEffect(() => {
    if (isHydrating) {
      return;
    }

    if (!pendingEnrollment && !isAuthenticated) {
      router.replace("/login");
      return;
    }

    let isActive = true;

    async function loadSetup() {
      setIsLoadingSetup(true);
      setError(null);

      try {
        const response = await beginTwoFactorEnrollment();
        if (isActive) {
          setSetup(response);
        }
      } catch (loadError) {
        if (isActive) {
          const message =
            loadError instanceof Error ? loadError.message : "Unable to start two-factor setup.";
          setError(message === "Request failed." ? "Unable to prepare your setup details. Please try again." : message);
        }
      } finally {
        if (isActive) {
          setIsLoadingSetup(false);
        }
      }
    }

    void loadSetup();

    return () => {
      isActive = false;
    };
  }, [beginTwoFactorEnrollment, isAuthenticated, isHydrating, pendingEnrollment, router]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);

    try {
      const user = await confirmTwoFactorEnrollment(code);

      if (!isDashboardRole(user.role)) {
        router.replace("/unauthorized");
        return;
      }

      router.replace(getDefaultRoute(user.role));
    } catch (submissionError) {
      const message =
        submissionError instanceof Error ? submissionError.message : "Invalid or expired code. Please try again.";
      setError(message === "Request failed." ? "Unable to finish setup. Please try again." : message);
    } finally {
      setIsSubmitting(false);
    }
  }

  function handleBack() {
    if (pendingEnrollment) {
      clearPendingEnrollment();
    }
    router.replace(currentUser ? "/profile" : "/login");
  }

  return (
    <PublicScreen className="bg-[var(--totp-background)] text-[var(--totp-ink)]">
      <PublicShell narrow className="justify-center">
        <div className="mb-8 flex items-center gap-3">
          <span className="inline-flex size-11 items-center justify-center rounded-2xl bg-[var(--totp-brand-mark-surface)] text-white shadow-[var(--totp-brand-mark-shadow)]">
            <Shield className="size-5" aria-hidden="true" />
          </span>
          <span className="text-3xl font-semibold tracking-tight text-[var(--totp-brand-ink)]">CCHIS</span>
        </div>

        <div className="w-full max-w-[720px] rounded-[2rem] border border-[var(--totp-card-border)] bg-[var(--totp-card-surface)] p-6 shadow-[var(--totp-card-shadow)] backdrop-blur md:p-8">
          <div className="mb-6 flex items-start gap-4">
            <div className="inline-flex size-12 shrink-0 items-center justify-center rounded-2xl bg-[color-mix(in_srgb,var(--dashboard-sidebar-title)_14%,white)] text-brand">
              <Smartphone className="size-6" aria-hidden="true" />
            </div>
            <div>
              <h1 className="text-4xl font-semibold leading-tight text-[var(--totp-ink)]">Set Up Two-Factor Authentication</h1>
              <p className="mt-2 text-sm text-[var(--totp-subtitle)]">
                Scan the QR code with your authenticator app, then enter the current 6-digit code to finish setup.
              </p>
            </div>
          </div>

          {!pendingEnrollment && !isAuthenticated && !isHydrating ? (
            <PublicAlert tone="warning">
              <span className="inline-flex items-center gap-2">
                <ShieldAlert className="size-4" aria-hidden="true" />
                Your setup session expired. Please return to login and start again.
              </span>
            </PublicAlert>
          ) : null}

          {error ? (
            <div className="mt-4">
              <PublicAlert tone="error">
                <span className="inline-flex items-center gap-2">
                  <ShieldAlert className="size-4" aria-hidden="true" />
                  {error}
                </span>
              </PublicAlert>
            </div>
          ) : null}

          {isLoadingSetup ? (
            <div className="mt-4">
              <PublicAlert>Preparing your two-factor setup details...</PublicAlert>
            </div>
          ) : setup ? (
            <div className="mt-6 space-y-5">
              <PublicAlert>Policy: {setup.two_factor_policy}</PublicAlert>

              <div className="grid gap-6 lg:grid-cols-[220px_minmax(0,1fr)]">
                <div className="flex justify-center rounded-[1.75rem] border border-panel-table-wrap bg-white p-4">
                  <QRCodeSVG value={setup.provisioning_uri} size={200} bgColor="#ffffff" fgColor="#102a2e" includeMargin />
                </div>
                <div className="space-y-3 text-sm text-panel-copy">
                  <p>Scan this QR code with Google Authenticator, Microsoft Authenticator, or another TOTP app.</p>
                  <p>If scanning is unavailable, use the manual setup key below.</p>
                  <button
                    type="button"
                    className="text-sm font-medium text-brand transition hover:text-[var(--login-link-hover)]"
                    onClick={() => setShowManualSetup((current) => !current)}
                    aria-expanded={showManualSetup}
                  >
                    {showManualSetup ? "Hide manual setup key" : "Can’t scan the QR code? Show manual setup key"}
                  </button>
                  {showManualSetup ? (
                    <div className="rounded-2xl border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] px-4 py-3 font-mono text-sm text-panel-strong">
                      {setup.manual_entry_key}
                    </div>
                  ) : null}
                </div>
              </div>
            </div>
          ) : null}

          <form className="mt-6 flex flex-col gap-4" onSubmit={handleSubmit}>
            <label className="flex flex-col gap-2">
              <span className="text-sm font-medium text-panel-copy">Verification code</span>
              <input
                id="code"
                name="code"
                inputMode="numeric"
                autoComplete="one-time-code"
                maxLength={6}
                value={code}
                onChange={(event) => setCode(event.target.value.replace(/\D/g, "").slice(0, 6))}
                placeholder="Enter the 6-digit code"
                required
                className="h-11 rounded-pill border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] px-4 text-sm text-panel-strong outline-none placeholder:text-panel-subtle focus:border-[var(--dashboard-icon-button-border)]"
              />
            </label>

            <Button className="w-full" type="submit" size="lg" disabled={isSubmitting || isLoadingSetup || !setup || code.length !== 6}>
              <KeyRound className="size-4" aria-hidden="true" />
              {isSubmitting ? "Finishing setup..." : "Finish Two-Factor Setup"}
            </Button>
          </form>

          <div className="mt-6 flex flex-col items-center gap-3 text-sm">
            <button type="button" className="inline-flex items-center gap-2 text-[var(--totp-link-muted)] transition hover:text-[var(--totp-link)]" onClick={handleBack}>
              <ArrowLeft className="size-4" aria-hidden="true" />
              Back
            </button>
            <Link href={currentUser ? "/profile" : "/login"} className="text-[var(--totp-link-muted)] transition hover:text-[var(--totp-link)]">
              Return without completing setup
            </Link>
          </div>
        </div>

        <PublicFooter />
      </PublicShell>
    </PublicScreen>
  );
}
