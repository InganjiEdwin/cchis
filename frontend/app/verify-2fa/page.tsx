"use client";

import { ArrowLeft, CircleAlert, KeyRound, Shield, ShieldAlert } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useRef, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { getDefaultRoute } from "@/lib/navigation";
import { isDashboardRole } from "@/lib/roles";

export default function VerifyTwoFactorPage() {
  const router = useRouter();
  const { clearPendingTwoFactor, isAuthenticated, isHydrating, pendingTwoFactor, verifyTwoFactor } =
    useAuth();
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const lastSubmittedCodeRef = useRef<string | null>(null);

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

  async function submitCode(codeToVerify: string) {
    if (isSubmitting || !pendingTwoFactor || codeToVerify.length !== 6 || lastSubmittedCodeRef.current === codeToVerify) {
      return;
    }

    setError(null);
    setIsSubmitting(true);
    lastSubmittedCodeRef.current = codeToVerify;

    try {
      const user = await verifyTwoFactor(codeToVerify);

      if (!isDashboardRole(user.role)) {
        router.replace("/unauthorized");
        return;
      }

      router.replace(getDefaultRoute(user.role));
    } catch (submissionError) {
      const message =
        submissionError instanceof Error ? submissionError.message : "Invalid or expired code. Please try again.";
      setError(
        message === "Request failed." ? "Verification request failed. Please try again." : message,
      );
      lastSubmittedCodeRef.current = null;
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await submitCode(code);
  }

  useEffect(() => {
    if (code.length === 6) {
      void submitCode(code);
      return;
    }

    lastSubmittedCodeRef.current = null;
  }, [code, pendingTwoFactor]);

  function handleBackToLogin() {
    clearPendingTwoFactor();
    router.replace("/login");
  }

  return (
    <div className="totp-screen">
      <div className="totp-glow totp-glow-left" aria-hidden="true" />
      <div className="totp-glow totp-glow-right" aria-hidden="true" />

      <main className="totp-shell">
        <section className="totp-brand">
          <div className="totp-brand-mark" aria-hidden="true">
            <Shield />
          </div>
          <span className="totp-brand-name">CCHIS</span>
        </section>

        <section className="totp-card">
          <div className="totp-copy">
            <h1 className="totp-title">Two-Factor Verification</h1>
            <p className="totp-subtitle">Enter the 6-digit code from your authenticator app to continue.</p>
          </div>

          {!pendingTwoFactor && !isHydrating ? (
            <div className="status status-warning">
              <ShieldAlert className="section-icon" aria-hidden="true" />
              Your verification session expired. Please return to login and start again.
            </div>
          ) : null}

          <form className="stack" onSubmit={handleSubmit}>
            <div className="totp-code-field">
              <label className="sr-only" htmlFor="code">
                Verification code
              </label>
              <input
                id="code"
                name="code"
                className="totp-code-input"
                inputMode="numeric"
                autoComplete="one-time-code"
                maxLength={6}
                value={code}
                onChange={(event) => setCode(event.target.value.replace(/\D/g, "").slice(0, 6))}
                placeholder="123456"
                required
                aria-describedby="totp-helper"
              />
              <div className="totp-code-grid" aria-hidden="true">
                {Array.from({ length: 6 }, (_, index) => (
                  <div key={index} className={`totp-code-cell${index < code.length ? " totp-code-cell-filled" : ""}`}>
                    {code[index] ?? "0"}
                  </div>
                ))}
              </div>
            </div>

            <p id="totp-helper" className="totp-helper">
              <CircleAlert className="section-icon" aria-hidden="true" />
              Code refreshes every 30 seconds in your authenticator app
            </p>

            {error ? (
              <div className="status status-error">
                <ShieldAlert className="section-icon" aria-hidden="true" />
                {error}
              </div>
            ) : null}

            <button
              className="totp-submit"
              type="submit"
              disabled={isSubmitting || isHydrating || !pendingTwoFactor || code.length !== 6}
            >
              <KeyRound className="section-icon" aria-hidden="true" />
              {isSubmitting ? "Verifying..." : "Verify Code"}
            </button>
          </form>

          <div className="totp-actions">
            <button type="button" className="totp-back-link" onClick={handleBackToLogin}>
              <ArrowLeft className="section-icon" aria-hidden="true" />
              Back to Login
            </button>
            <Link href="/login" className="totp-secondary-link">
              Restart sign-in flow
            </Link>
          </div>
        </section>

        <footer className="totp-footer">
          <div className="totp-footer-links">
            <Link href="/privacy" className="totp-footer-link">
              Privacy Policy
            </Link>
            <Link href="/terms" className="totp-footer-link">
              Terms of Service
            </Link>
          </div>
        </footer>
      </main>
    </div>
  );
}
