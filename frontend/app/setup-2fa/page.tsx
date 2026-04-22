"use client";

import { ArrowLeft, KeyRound, Shield, ShieldAlert, Smartphone } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import { QRCodeSVG } from "qrcode.react";

import { useAuth } from "@/components/auth-provider";
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

        <section className="totp-card setup-totp-card">
          <div className="totp-copy">
            <div className="setup-totp-heading">
              <div className="setup-totp-icon" aria-hidden="true">
                <Smartphone />
              </div>
              <div>
                <h1 className="totp-title setup-totp-title">Set Up Two-Factor Authentication</h1>
                <p className="totp-subtitle">
                  Scan the QR code with your authenticator app, then enter the current 6-digit code to finish setup.
                </p>
              </div>
            </div>
          </div>

          {!pendingEnrollment && !isAuthenticated && !isHydrating ? (
            <div className="status status-warning">
              <ShieldAlert className="section-icon" aria-hidden="true" />
              Your setup session expired. Please return to login and start again.
            </div>
          ) : null}

          {error ? (
            <div className="status status-error">
              <ShieldAlert className="section-icon" aria-hidden="true" />
              {error}
            </div>
          ) : null}

          {isLoadingSetup ? (
            <div className="status">
              <KeyRound className="section-icon" aria-hidden="true" />
              Preparing your two-factor setup details...
            </div>
          ) : setup ? (
            <div className="setup-totp-block">
              <div className="status">
                <KeyRound className="section-icon" aria-hidden="true" />
                Policy: {setup.two_factor_policy}
              </div>

              <div className="two-factor-qr-card setup-two-factor-qr-card">
                <div className="two-factor-qr-frame" aria-label="Two-factor QR code">
                  <QRCodeSVG
                    value={setup.provisioning_uri}
                    size={200}
                    bgColor="#ffffff"
                    fgColor="#102a2e"
                    includeMargin
                  />
                </div>
                <div className="two-factor-qr-copy">
                  <p className="muted" style={{ margin: 0 }}>
                    Scan this QR code with Google Authenticator, Microsoft Authenticator, or another TOTP app.
                  </p>
                  <p className="muted" style={{ margin: 0 }}>
                    If scanning is unavailable, use the manual setup key below.
                  </p>
                </div>
              </div>

              <button
                type="button"
                className="totp-secondary-link setup-totp-toggle"
                onClick={() => setShowManualSetup((current) => !current)}
                aria-expanded={showManualSetup}
              >
                {showManualSetup ? "Hide manual setup key" : "Can’t scan the QR code? Show manual setup key"}
              </button>

              {showManualSetup ? (
                <div className="setup-totp-manual">
                  <label htmlFor="manual-entry-key" className="sr-only">
                    Manual entry key
                  </label>
                  <input
                    id="manual-entry-key"
                    value={setup.manual_entry_key}
                    readOnly
                    className="setup-totp-manual-key"
                  />
                </div>
              ) : null}
            </div>
          ) : null}

          <form className="stack setup-totp-form" onSubmit={handleSubmit}>
            <div className="setup-totp-code-field">
              <label className="sr-only" htmlFor="code">
                Verification code
              </label>
              <input
                id="code"
                name="code"
                className="setup-totp-code-input"
                inputMode="numeric"
                autoComplete="one-time-code"
                maxLength={6}
                value={code}
                onChange={(event) => setCode(event.target.value.replace(/\D/g, "").slice(0, 6))}
                placeholder="Enter the 6-digit code"
                required
              />
            </div>

            <button
              className="totp-submit"
              type="submit"
              disabled={isSubmitting || isLoadingSetup || !setup || code.length !== 6}
            >
              <KeyRound className="section-icon" aria-hidden="true" />
              {isSubmitting ? "Finishing setup..." : "Finish Two-Factor Setup"}
            </button>
          </form>

          <div className="totp-actions">
            <button type="button" className="totp-back-link" onClick={handleBack}>
              <ArrowLeft className="section-icon" aria-hidden="true" />
              Back
            </button>
            <Link href={currentUser ? "/profile" : "/login"} className="totp-secondary-link">
              Return without completing setup
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
