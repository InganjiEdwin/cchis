"use client";

import { ArrowRight, Mail, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { FormEvent, useState } from "react";

import { requestPasswordReset } from "@/lib/auth";
import { Button } from "@/components/ui/button";
import { InputShell } from "@/components/ui/input-shell";
import {
  PublicAlert,
  PublicFooter,
  PublicScreen,
  PublicShell,
  PublicTopbar,
  PublicCard,
  SectionBackLink,
} from "@/components/ui/public-shell";

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
    <PublicScreen className="bg-[var(--forgot-background)]">
      <PublicTopbar showHelp />
      <PublicShell narrow className="justify-center">
        <PublicCard className="max-w-[560px]">
          <div className="mx-auto mb-6 flex size-24 items-center justify-center rounded-[2rem] bg-[var(--forgot-icon-surface)] text-[var(--forgot-icon-ink)]">
            <ShieldCheck className="size-12" aria-hidden="true" />
          </div>

          <div className="mb-6 text-center">
            <h1 className="text-4xl font-semibold tracking-tight text-[var(--forgot-title)]">Password Recovery</h1>
            <p className="mt-2 text-sm text-[var(--forgot-subtitle)]">
              Enter your email address or username and we&apos;ll send instructions to help you reset your password.
            </p>
          </div>

          <form className="flex flex-col gap-4" onSubmit={handleSubmit}>
            <InputShell
              id="identifier"
              label="Email address or username"
              autoComplete="username"
              value={identifier}
              onChange={(event) => setIdentifier(event.target.value)}
              placeholder="name@example.org"
              icon={<Mail className="size-4" aria-hidden="true" />}
            />

            {error ? <PublicAlert tone="error">{error}</PublicAlert> : null}
            {successMessage ? <PublicAlert tone="success">{successMessage}</PublicAlert> : null}

            <Button type="submit" size="lg" disabled={isSubmitting} className="w-full">
              {isSubmitting ? "Sending reset instructions..." : "Reset Password"}
              <ArrowRight className="size-4" aria-hidden="true" />
            </Button>
          </form>

          <div className="mt-6">
            <SectionBackLink />
          </div>
        </PublicCard>
        <PublicFooter />
      </PublicShell>
    </PublicScreen>
  );
}
