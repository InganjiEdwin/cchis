"use client";

import { ArrowLeft, CircleHelp, Eye, EyeOff, LockKeyhole, Shield } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, Suspense, useEffect, useMemo, useState } from "react";

import { confirmPasswordReset, validatePasswordResetToken } from "@/lib/auth";

type ResetState = "checking" | "ready" | "invalid" | "success";

export default function ResetPasswordPage() {
  return (
    <Suspense fallback={<ResetPasswordPageFallback />}>
      <ResetPasswordPageContent />
    </Suspense>
  );
}

function ResetPasswordPageFallback() {
  return (
    <div className="reset-screen">
      <header className="forgot-topbar">
        <Link href="/login" className="forgot-brand">
          CHIS
        </Link>
      </header>

      <main className="reset-shell">
        <section className="reset-card">
          <div className="forgot-copy">
            <h1 className="reset-title">Create New Password</h1>
            <p className="reset-subtitle">Preparing your password reset screen...</p>
          </div>
          <div className="status reset-status-card">Checking your reset link...</div>
        </section>
      </main>
    </div>
  );
}

function ResetPasswordPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = useMemo(() => searchParams.get("token")?.trim() ?? "", [searchParams]);
  const [state, setState] = useState<ResetState>("checking");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [showNewPassword, setShowNewPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);

  useEffect(() => {
    const checkToken = async () => {
      if (!token) {
        setState("invalid");
        setError("This password reset link is invalid or has expired.");
        return;
      }

      try {
        await validatePasswordResetToken(token);
        setState("ready");
      } catch (validationError) {
        setState("invalid");
        setError(
          validationError instanceof Error
            ? validationError.message
            : "This password reset link is invalid or has expired.",
        );
      }
    };

    setError(null);
    setSuccessMessage(null);
    setState("checking");
    void checkToken();
  }, [token]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);

    if (newPassword !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }

    setIsSubmitting(true);

    try {
      const response = await confirmPasswordReset(token, newPassword);
      setSuccessMessage(response.detail);
      setState("success");
      setNewPassword("");
      setConfirmPassword("");
    } catch (submissionError) {
      setError(
        submissionError instanceof Error
          ? submissionError.message
          : "We couldn't update your password right now. Please try again.",
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="reset-screen">
      <header className="forgot-topbar">
        <Link href="/login" className="forgot-brand">
          CHIS
        </Link>
        <div className="forgot-topbar-actions">
          <Link href="/login" className="forgot-topbar-link">
            Back to Login
          </Link>
          <span className="forgot-help-badge" aria-hidden="true">
            <CircleHelp />
          </span>
        </div>
      </header>

      <main className="reset-shell">
        <section className="reset-card">
          <div className="forgot-copy">
            <h1 className="reset-title">
              {state === "success" ? "Password Updated" : state === "invalid" ? "Reset Link Unavailable" : "Create New Password"}
            </h1>
            <p className="reset-subtitle">
              {state === "success"
                ? "Your password has been updated successfully. You can now return to the login screen."
                : state === "invalid"
                  ? "This reset link is no longer available. Request a new one to continue."
                  : "Enter and confirm your new password."}
            </p>
          </div>

          {state === "checking" ? (
            <div className="status reset-status-card">Checking your reset link...</div>
          ) : null}

          {state === "ready" ? (
            <form className="stack" onSubmit={handleSubmit}>
              <div className="login-field">
                <label htmlFor="new_password">New Password</label>
                <div className="login-input-wrap forgot-input-wrap">
                  <LockKeyhole className="login-input-icon" aria-hidden="true" />
                  <input
                    id="new_password"
                    name="new_password"
                    type={showNewPassword ? "text" : "password"}
                    autoComplete="new-password"
                    value={newPassword}
                    onChange={(event) => setNewPassword(event.target.value)}
                    placeholder="Enter your new password"
                    required
                  />
                  <button
                    type="button"
                    className="login-visibility-button"
                    onClick={() => setShowNewPassword((current) => !current)}
                    aria-label={showNewPassword ? "Hide new password" : "Show new password"}
                  >
                    {showNewPassword ? <EyeOff aria-hidden="true" /> : <Eye aria-hidden="true" />}
                  </button>
                </div>
              </div>

              <div className="login-field">
                <label htmlFor="confirm_password">Confirm Password</label>
                <div className="login-input-wrap forgot-input-wrap">
                  <LockKeyhole className="login-input-icon" aria-hidden="true" />
                  <input
                    id="confirm_password"
                    name="confirm_password"
                    type={showConfirmPassword ? "text" : "password"}
                    autoComplete="new-password"
                    value={confirmPassword}
                    onChange={(event) => setConfirmPassword(event.target.value)}
                    placeholder="Confirm your new password"
                    required
                  />
                  <button
                    type="button"
                    className="login-visibility-button"
                    onClick={() => setShowConfirmPassword((current) => !current)}
                    aria-label={showConfirmPassword ? "Hide confirm password" : "Show confirm password"}
                  >
                    {showConfirmPassword ? <EyeOff aria-hidden="true" /> : <Eye aria-hidden="true" />}
                  </button>
                </div>
              </div>

              {error ? <div className="status status-error login-error-banner">{error}</div> : null}

              <button className="reset-submit" type="submit" disabled={isSubmitting}>
                {isSubmitting ? "Updating password..." : "Update Password"}
              </button>
            </form>
          ) : null}

          {state === "invalid" ? (
            <div className="stack reset-state-actions">
              {error ? <div className="status status-error login-error-banner">{error}</div> : null}
              <Link href="/forgot-password" className="reset-secondary-link">
                Request new reset link
              </Link>
            </div>
          ) : null}

          {state === "success" ? (
            <div className="stack reset-state-actions">
              {successMessage ? <div className="status forgot-success-banner">{successMessage}</div> : null}
              <button type="button" className="reset-submit" onClick={() => router.replace("/login")}>
                Back to Login
              </button>
            </div>
          ) : null}

          {(state === "ready" || state === "checking") ? (
            <Link href="/login" className="forgot-back-link">
              <ArrowLeft className="section-icon" aria-hidden="true" />
              Back to Login
            </Link>
          ) : null}
        </section>
      </main>

      <footer className="login-footer">
        <p>&copy; 2026 Climate Health Intelligence System. All rights reserved.</p>
        <div className="login-footer-links">
          <Link href="/privacy" className="login-footer-link">
            Privacy Policy
          </Link>
          <Link href="/terms" className="login-footer-link">
            Terms of Service
          </Link>
        </div>
      </footer>
    </div>
  );
}
