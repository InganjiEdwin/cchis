"use client";

import { ArrowLeft, CircleAlert, KeyRound, Shield, ShieldAlert } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ClipboardEvent, FormEvent, useEffect, useRef, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { Button } from "@/components/ui/button";
import { PublicAlert, PublicFooter, PublicGlow, PublicScreen, PublicShell } from "@/components/ui/public-shell";
import { persistRecoveryCodeLoginNotice } from "@/lib/auth";
import { getDefaultRoute } from "@/lib/navigation";
import { isDashboardRole } from "@/lib/roles";

type VerificationMode = "totp" | "recovery";
const RECOVERY_CODE_NORMALIZED_LENGTH = 17;

function normalizeRecoveryCodeInput(value: string) {
  return value.toUpperCase().replace(/[^A-Z0-9 -]/g, "").slice(0, 24);
}

function getRecoveryCodeLength(value: string) {
  return value.replace(/[^A-Za-z0-9]/g, "").length;
}

export default function VerifyTwoFactorPage() {
  const router = useRouter();
  const { clearPendingTwoFactor, isAuthenticated, isHydrating, pendingTwoFactor, verifyTwoFactor } =
    useAuth();
  const [code, setCode] = useState("");
  const [verificationMode, setVerificationMode] = useState<VerificationMode>("totp");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const lastSubmittedCodeRef = useRef<string | null>(null);
  const codeInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (isHydrating) {
      return;
    }

    if (isAuthenticated) {
      router.replace("/overview");
      return;
    }

    if (!pendingTwoFactor) {
      router.replace("/login");
    }
  }, [isAuthenticated, isHydrating, pendingTwoFactor, router]);

  useEffect(() => {
    if (!pendingTwoFactor || isHydrating) {
      return;
    }

    const frame = window.requestAnimationFrame(() => {
      codeInputRef.current?.focus();
    });

    return () => window.cancelAnimationFrame(frame);
  }, [isHydrating, pendingTwoFactor]);

  async function submitCode(codeToVerify: string, mode: VerificationMode = verificationMode) {
    const isCompleteCode =
      mode === "totp" ? codeToVerify.length === 6 : getRecoveryCodeLength(codeToVerify) === RECOVERY_CODE_NORMALIZED_LENGTH;
    const submissionKey = `${mode}:${codeToVerify}`;

    if (isSubmitting || !pendingTwoFactor || !isCompleteCode || lastSubmittedCodeRef.current === submissionKey) {
      return;
    }

    setError(null);
    setIsSubmitting(true);
    lastSubmittedCodeRef.current = submissionKey;

    try {
      const verification = await verifyTwoFactor(codeToVerify);
      const user = verification.user;

      if (!isDashboardRole(user.role)) {
        router.replace("/unauthorized");
        return;
      }

      if (
        verification.second_factor_method === "recovery_code" &&
        verification.recovery_codes_low &&
        typeof verification.recovery_codes_remaining === "number"
      ) {
        persistRecoveryCodeLoginNotice(verification.recovery_codes_remaining);
      }

      router.replace(getDefaultRoute(user.role));
    } catch (submissionError) {
      const message =
        submissionError instanceof Error ? submissionError.message : "Invalid or expired code. Please try again.";
      setError(message === "Request failed." ? "Verification request failed. Please try again." : message);
      lastSubmittedCodeRef.current = null;
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await submitCode(code);
  }

  function handlePaste(event: ClipboardEvent<HTMLDivElement | HTMLInputElement>) {
    const rawPasted = event.clipboardData.getData("text");
    const pasted =
      verificationMode === "totp"
        ? rawPasted.replace(/\D/g, "").slice(0, 6)
        : normalizeRecoveryCodeInput(rawPasted);

    if (!pasted) {
      return;
    }

    event.preventDefault();
    setCode(pasted);
  }

  useEffect(() => {
    if (verificationMode === "totp" && code.length === 6) {
      void submitCode(code, "totp");
      return;
    }

    lastSubmittedCodeRef.current = null;
  }, [code, pendingTwoFactor, verificationMode]);

  function handleModeChange(nextMode: VerificationMode) {
    setVerificationMode(nextMode);
    setCode("");
    setError(null);
    lastSubmittedCodeRef.current = null;
    window.requestAnimationFrame(() => codeInputRef.current?.focus());
  }

  function handleBackToLogin() {
    clearPendingTwoFactor();
    router.replace("/login");
  }

  return (
    <PublicScreen className="bg-[var(--totp-background)] text-[var(--totp-ink)]">
      <PublicGlow side="left" />
      <PublicGlow side="right" />
      <PublicShell narrow className="justify-center">
        <div className="mb-8 flex items-center gap-3">
          <span className="inline-flex size-11 items-center justify-center rounded-2xl bg-[var(--totp-brand-mark-surface)] text-white shadow-[var(--totp-brand-mark-shadow)]">
            <Shield className="size-5" aria-hidden="true" />
          </span>
          <span className="text-3xl font-semibold tracking-tight text-[var(--totp-brand-ink)]">CCHIS</span>
        </div>

        <div className="w-full max-w-[440px] rounded-[2rem] border border-[var(--totp-card-border)] bg-[var(--totp-card-surface)] p-6 shadow-[var(--totp-card-shadow)] backdrop-blur md:p-8">
          <div className="mb-6">
            <h1 className="text-4xl font-semibold leading-tight text-[var(--totp-ink)]">Two-Factor Verification</h1>
            <p className="mt-2 text-sm text-[var(--totp-subtitle)]">
              {verificationMode === "totp"
                ? "Enter the 6-digit code from your authenticator app to continue."
                : "Enter one of your saved recovery codes to continue."}
            </p>
          </div>

          {!pendingTwoFactor && !isHydrating ? (
            <PublicAlert tone="warning">
              <span className="inline-flex items-center gap-2">
                <ShieldAlert className="size-4" aria-hidden="true" />
                Your verification session expired. Please return to login and start again.
              </span>
            </PublicAlert>
          ) : null}

          <form className="mt-5 flex flex-col gap-4" onSubmit={handleSubmit}>
            <div className="grid grid-cols-2 gap-1 rounded-[1rem] border border-[var(--totp-code-cell-border)] bg-[var(--totp-code-cell-surface)] p-1">
              <button
                type="button"
                onClick={() => handleModeChange("totp")}
                aria-pressed={verificationMode === "totp"}
                className={`min-h-10 rounded-[0.8rem] text-sm font-semibold transition ${
                  verificationMode === "totp"
                    ? "bg-[var(--login-submit-start)] text-white"
                    : "text-[var(--totp-subtitle)] hover:bg-[color-mix(in_srgb,var(--dashboard-table-line)_30%,transparent)]"
                }`}
              >
                Authenticator code
              </button>
              <button
                type="button"
                onClick={() => handleModeChange("recovery")}
                aria-pressed={verificationMode === "recovery"}
                className={`min-h-10 rounded-[0.8rem] text-sm font-semibold transition ${
                  verificationMode === "recovery"
                    ? "bg-[var(--login-submit-start)] text-white"
                    : "text-[var(--totp-subtitle)] hover:bg-[color-mix(in_srgb,var(--dashboard-table-line)_30%,transparent)]"
                }`}
              >
                Recovery code
              </button>
            </div>

            <div className="flex flex-col gap-3">
              <label className="text-sm font-semibold text-[var(--totp-subtitle)]" htmlFor="code">
                Authenticator or recovery code
              </label>
              {verificationMode === "totp" ? (
                <>
                  <input
                    id="code"
                    name="code"
                    ref={codeInputRef}
                    className="sr-only"
                    autoFocus
                    inputMode="numeric"
                    autoComplete="one-time-code"
                    maxLength={6}
                    value={code}
                    onChange={(event) => setCode(event.target.value.replace(/\D/g, "").slice(0, 6))}
                    onPaste={handlePaste}
                    placeholder="123456"
                    required
                    aria-describedby="totp-helper"
                  />
                  <div
                    className="grid cursor-text grid-cols-6 gap-2"
                    aria-hidden="true"
                    onClick={() => codeInputRef.current?.focus()}
                    onPaste={handlePaste}
                    onMouseDown={(event) => {
                      event.preventDefault();
                      codeInputRef.current?.focus();
                    }}
                  >
                    {Array.from({ length: 6 }, (_, index) => (
                      <div
                        key={index}
                        className={`flex h-12 items-center justify-center rounded-2xl border text-xl font-semibold ${
                          index < code.length
                            ? "border-[color-mix(in_srgb,var(--totp-code-cell-filled-border)_92%,white)] bg-[var(--dashboard-icon-button-surface)] text-[var(--totp-code-cell-filled-ink)] shadow-[var(--totp-code-cell-filled-shadow)]"
                            : "border-[var(--totp-code-cell-border)] bg-[var(--totp-code-cell-surface)] text-[var(--totp-code-cell-ink)]"
                        }`}
                      >
                        {code[index] ?? "0"}
                      </div>
                    ))}
                  </div>
                </>
              ) : (
                <input
                  id="code"
                  name="code"
                  ref={codeInputRef}
                  autoFocus
                  autoComplete="one-time-code"
                  value={code}
                  onChange={(event) => setCode(normalizeRecoveryCodeInput(event.target.value))}
                  onPaste={handlePaste}
                  placeholder="CCHIS-XXXX-XXXX-XXXX"
                  required
                  aria-describedby="totp-helper"
                  className="h-12 rounded-[1rem] border border-[var(--totp-code-cell-border)] bg-[var(--dashboard-icon-button-surface)] px-4 text-center font-mono text-sm font-semibold text-[var(--totp-code-cell-filled-ink)] outline-none focus:border-[var(--totp-code-cell-filled-border)]"
                />
              )}
            </div>

            <p id="totp-helper" className="inline-flex items-center gap-2 text-sm text-[var(--totp-helper)]">
              <CircleAlert className="size-4" aria-hidden="true" />
              {verificationMode === "totp"
                ? "Code refreshes every 30 seconds in your authenticator app"
                : "Recovery codes are one-time use"}
            </p>

            {error ? (
              <PublicAlert tone="error">
                <span className="inline-flex items-center gap-2">
                  <ShieldAlert className="size-4" aria-hidden="true" />
                  {error}
                </span>
              </PublicAlert>
            ) : null}

            <Button
              type="submit"
              size="lg"
              disabled={
                isSubmitting ||
                isHydrating ||
                !pendingTwoFactor ||
                (verificationMode === "totp"
                  ? code.length !== 6
                  : getRecoveryCodeLength(code) !== RECOVERY_CODE_NORMALIZED_LENGTH)
              }
              className="w-full"
            >
              <KeyRound className="size-4" aria-hidden="true" />
              {isSubmitting ? "Verifying..." : verificationMode === "totp" ? "Verify Code" : "Use Recovery Code"}
            </Button>
          </form>

          <div className="mt-6 flex flex-col items-center gap-3 text-sm">
            <button type="button" className="inline-flex items-center gap-2 text-[var(--totp-link-muted)] transition hover:text-[var(--totp-link)]" onClick={handleBackToLogin}>
              <ArrowLeft className="size-4" aria-hidden="true" />
              Back to Login
            </button>
            <Link href="/login" className="text-[var(--totp-link-muted)] transition hover:text-[var(--totp-link)]">
              Restart sign-in flow
            </Link>
          </div>
        </div>

        <PublicFooter />
      </PublicShell>
    </PublicScreen>
  );
}
