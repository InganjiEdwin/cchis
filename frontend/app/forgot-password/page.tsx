"use client";

import { ArrowLeft, ArrowRight, CircleHelp, Mail, Shield } from "lucide-react";
import Link from "next/link";
import { FormEvent, useState } from "react";

import { requestPasswordReset } from "@/lib/auth";

export default function ForgotPasswordPage() {
  const [identifier, setIdentifier] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSuccessMessage(null);
    setIsSubmitting(true);

    try {
      const response = await requestPasswordReset(identifier);
      setSuccessMessage(response.detail);
    } catch (submissionError) {
      setError(
        submissionError instanceof Error
          ? submissionError.message
          : "We couldn't start password recovery right now. Please try again.",
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="forgot-screen">
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

      <main className="forgot-shell">
        <section className="forgot-card">
          <div className="forgot-icon" aria-hidden="true">
            <Shield />
          </div>

          <div className="forgot-copy">
            <h1 className="forgot-title">Password Recovery</h1>
            <p className="forgot-subtitle">
              Enter your email address or username and we&apos;ll send instructions to help you reset your
              password.
            </p>
          </div>

          <form className="stack" onSubmit={handleSubmit}>
            <div className="login-field">
              <label htmlFor="identifier">Email address or username</label>
              <div className="login-input-wrap forgot-input-wrap">
                <Mail className="login-input-icon" aria-hidden="true" />
                <input
                  id="identifier"
                  name="identifier"
                  autoComplete="username"
                  value={identifier}
                  onChange={(event) => setIdentifier(event.target.value)}
                  placeholder="name@example.org"
                  required
                />
              </div>
            </div>

            {error ? <div className="status status-error login-error-banner">{error}</div> : null}
            {successMessage ? <div className="status forgot-success-banner">{successMessage}</div> : null}

            <button className="forgot-submit" type="submit" disabled={isSubmitting}>
              {isSubmitting ? "Sending reset instructions..." : "Reset Password"}
              <ArrowRight className="section-icon forgot-submit-icon" aria-hidden="true" />
            </button>
          </form>

          <Link href="/login" className="forgot-back-link">
            <ArrowLeft className="section-icon" aria-hidden="true" />
            Back to Login
          </Link>
        </section>

        <footer className="forgot-footer">
          <div className="forgot-footer-links">
            <Link href="/privacy" className="forgot-footer-link">
              Privacy Policy
            </Link>
            <Link href="/terms" className="forgot-footer-link">
              Terms of Service
            </Link>
          </div>
        </footer>
      </main>
    </div>
  );
}
