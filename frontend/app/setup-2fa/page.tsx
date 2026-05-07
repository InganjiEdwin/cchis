"use client";

import { ArrowLeft, CheckCircle2, Copy, Download, KeyRound, Printer, ShieldAlert, Smartphone } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import { QRCodeSVG } from "qrcode.react";

import { useAuth } from "@/components/auth-provider";
import { Button } from "@/components/ui/button";
import {
  PublicAlert,
  BrandLockup,
  PublicFooter,
  PublicScreen,
  PublicShell,
} from "@/components/ui/public-shell";
import { buildPolicyReviewRoute, getDefaultRoute } from "@/lib/navigation";
import { requiresPolicyAcceptance, type CurrentUser } from "@/lib/auth";

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
  const [confirmedUser, setConfirmedUser] = useState<CurrentUser | null>(null);
  const [recoveryCodes, setRecoveryCodes] = useState<string[]>([]);
  const [hasSavedRecoveryCodes, setHasSavedRecoveryCodes] = useState(false);
  const [copyMessage, setCopyMessage] = useState<string | null>(null);

  useEffect(() => {
    if (isHydrating) {
      return;
    }

    if (recoveryCodes.length > 0) {
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
  }, [beginTwoFactorEnrollment, isAuthenticated, isHydrating, pendingEnrollment, recoveryCodes.length, router]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);

    try {
      const response = await confirmTwoFactorEnrollment(code);
      const user = response.user;

      const nextRoute = getDefaultRoute(user.role);
      if (nextRoute === "/unauthorized") {
        router.replace("/unauthorized");
        return;
      }

      const codes = Array.isArray(response.recovery_codes) ? response.recovery_codes : [];
      setConfirmedUser(user);
      setRecoveryCodes(codes);
      setHasSavedRecoveryCodes(false);
      setCopyMessage(null);

      if (codes.length === 0) {
        router.replace(requiresPolicyAcceptance(user) ? buildPolicyReviewRoute(nextRoute) : nextRoute);
      }
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

  async function handleCopyRecoveryCodes() {
    if (recoveryCodes.length === 0) {
      return;
    }

    try {
      await navigator.clipboard.writeText(recoveryCodes.join("\n"));
      setCopyMessage("Copied");
    } catch {
      setCopyMessage("Copy unavailable");
    }
  }

  function handleDownloadRecoveryCodes() {
    if (recoveryCodes.length === 0) {
      return;
    }

    const blob = new Blob(
      [
        [
          "CCHIS recovery codes",
          "",
          ...recoveryCodes,
          "",
          "Each code can be used once.",
        ].join("\n"),
      ],
      { type: "text/plain" },
    );
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "cchis-recovery-codes.txt";
    link.click();
    window.URL.revokeObjectURL(url);
    setCopyMessage("Download started");
  }

  function handlePrintRecoveryCodes() {
    if (recoveryCodes.length === 0) {
      return;
    }

    window.print();
    setCopyMessage("Print dialog opened");
  }

  function handleContinue() {
    const user = confirmedUser || currentUser;

    if (!user) {
      router.replace("/login");
      return;
    }

    const nextRoute = getDefaultRoute(user.role);
    router.replace(requiresPolicyAcceptance(user) ? buildPolicyReviewRoute(nextRoute) : nextRoute);
  }

  return (
    <PublicScreen className="bg-[var(--totp-background)] text-[var(--totp-ink)]">
      <PublicShell narrow className="justify-center">
        <BrandLockup className="mb-8 md:mb-8" />

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

          {recoveryCodes.length > 0 ? (
            <div className="mt-6 space-y-5">
              <PublicAlert tone="success">
                <span className="inline-flex items-center gap-2">
                  <CheckCircle2 className="size-4" aria-hidden="true" />
                  Two-factor authentication is enabled.
                </span>
              </PublicAlert>

              <div>
                <h2 className="text-2xl font-semibold text-panel-strong">Save your recovery codes</h2>
                <p className="mt-2 text-sm leading-6 text-panel-copy">
                  Each code works once if your authenticator is unavailable. Store them somewhere private; they will not be shown again after you leave this screen.
                </p>
              </div>

              <div className="rounded-[1.5rem] border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] p-4">
                <div className="grid gap-2 sm:grid-cols-2">
                  {recoveryCodes.map((recoveryCode) => (
                    <code
                      key={recoveryCode}
                      className="rounded-[0.9rem] border border-panel-table-wrap bg-[color-mix(in_srgb,var(--dashboard-table-line)_20%,transparent)] px-3 py-2 text-center font-mono text-sm font-semibold text-panel-strong"
                    >
                      {recoveryCode}
                    </code>
                  ))}
                </div>
              </div>

              <div className="grid gap-3 sm:grid-cols-3">
                <Button type="button" variant="secondary" onClick={() => void handleCopyRecoveryCodes()}>
                  <Copy className="size-4" aria-hidden="true" />
                  Copy codes
                </Button>
                <Button type="button" variant="secondary" onClick={handleDownloadRecoveryCodes}>
                  <Download className="size-4" aria-hidden="true" />
                  Download codes
                </Button>
                <Button type="button" variant="secondary" onClick={handlePrintRecoveryCodes}>
                  <Printer className="size-4" aria-hidden="true" />
                  Print codes
                </Button>
              </div>

              {copyMessage ? <p className="text-sm font-medium text-panel-muted">{copyMessage}</p> : null}

              <label className="flex items-start gap-3 rounded-[1rem] border border-panel-table-wrap bg-[color-mix(in_srgb,var(--dashboard-table-line)_18%,transparent)] px-4 py-3 text-sm font-medium text-panel-copy">
                <input
                  type="checkbox"
                  checked={hasSavedRecoveryCodes}
                  onChange={(event) => setHasSavedRecoveryCodes(event.target.checked)}
                  className="mt-1 size-4 accent-[var(--login-submit-start)]"
                />
                I have saved these recovery codes.
              </label>

              <Button className="w-full" type="button" size="lg" disabled={!hasSavedRecoveryCodes} onClick={handleContinue}>
                Continue
              </Button>
            </div>
          ) : isLoadingSetup ? (
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

          {recoveryCodes.length === 0 ? (
            <>
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
                  Back to profile summary
                </button>
                <Link href={currentUser ? "/profile" : "/login"} className="text-[var(--totp-link-muted)] transition hover:text-[var(--totp-link)]">
                  Return to profile summary without completing setup
                </Link>
              </div>
            </>
          ) : null}
        </div>

        <PublicFooter />
      </PublicShell>
    </PublicScreen>
  );
}
