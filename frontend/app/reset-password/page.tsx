"use client";

import { Suspense, useEffect, useMemo, useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";

import { Button } from "@/components/ui/button";
import { PasswordField } from "@/components/ui/password-field";
import {
  PublicAlert,
  PublicCard,
  PublicFooter,
  PublicScreen,
  PublicShell,
  PublicTopbar,
  SectionBackLink,
} from "@/components/ui/public-shell";
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
    <PublicScreen className="bg-[var(--forgot-background)]">
      <PublicTopbar showHelp />
      <PublicShell narrow className="justify-center">
        <PublicCard className="max-w-[560px]">
          <div className="text-center">
            <h1 className="text-4xl font-semibold tracking-tight text-[var(--forgot-title)]">Create New Password</h1>
            <p className="mt-2 text-sm text-[var(--forgot-subtitle)]">Preparing your password reset screen...</p>
          </div>
          <div className="mt-6">
            <PublicAlert>Checking your reset link...</PublicAlert>
          </div>
        </PublicCard>
      </PublicShell>
    </PublicScreen>
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
    <PublicScreen className="bg-[var(--forgot-background)]">
      <PublicTopbar showHelp />
      <PublicShell narrow className="justify-center">
        <PublicCard className="max-w-[560px]">
          <div className="text-center">
            <h1 className="text-4xl font-semibold tracking-tight text-[var(--forgot-title)]">
              {state === "success" ? "Password Updated" : state === "invalid" ? "Reset Link Unavailable" : "Create New Password"}
            </h1>
            <p className="mt-2 text-sm text-[var(--forgot-subtitle)]">
              {state === "success"
                ? "Your password has been updated successfully. You can now return to the login screen."
                : state === "invalid"
                  ? "This reset link is no longer available. Request a new one to continue."
                  : "Enter and confirm your new password."}
            </p>
          </div>

          {state === "checking" ? (
            <div className="mt-6">
              <PublicAlert>Checking your reset link...</PublicAlert>
            </div>
          ) : null}

          {state === "ready" ? (
            <form className="mt-6 flex flex-col gap-4" onSubmit={handleSubmit}>
              <PasswordField
                id="new_password"
                label="New Password"
                autoComplete="new-password"
                value={newPassword}
                onChange={setNewPassword}
                placeholder="Enter your new password"
              />

              <PasswordField
                id="confirm_password"
                label="Confirm Password"
                autoComplete="new-password"
                value={confirmPassword}
                onChange={setConfirmPassword}
                placeholder="Confirm your new password"
              />

              {error ? <PublicAlert tone="error">{error}</PublicAlert> : null}

              <Button className="w-full" size="lg" type="submit" disabled={isSubmitting}>
                {isSubmitting ? "Updating password..." : "Update Password"}
              </Button>
            </form>
          ) : null}

          {state === "invalid" ? (
            <div className="mt-6 flex flex-col gap-4">
              {error ? <PublicAlert tone="error">{error}</PublicAlert> : null}
              <Link href="/forgot-password" className="inline-flex justify-center rounded-pill border border-panel-table-wrap px-4 py-3 text-sm font-semibold text-panel-copy transition hover:text-panel-strong">
                Request new reset link
              </Link>
            </div>
          ) : null}

          {state === "success" ? (
            <div className="mt-6 flex flex-col gap-4">
              {successMessage ? <PublicAlert tone="success">{successMessage}</PublicAlert> : null}
              <Button className="w-full" size="lg" onClick={() => router.replace("/login")}>
                Back to Login
              </Button>
            </div>
          ) : null}

          {state === "ready" || state === "checking" ? (
            <div className="mt-6">
              <SectionBackLink />
            </div>
          ) : null}
        </PublicCard>
        <PublicFooter />
      </PublicShell>
    </PublicScreen>
  );
}
