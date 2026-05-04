"use client";

import { ArrowRight, KeyRound, Mail, ShieldAlert } from "lucide-react";
import Link from "next/link";
import Script from "next/script";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useRef, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { Button } from "@/components/ui/button";
import { InputShell } from "@/components/ui/input-shell";
import { PasswordField } from "@/components/ui/password-field";
import {
  BrandLockup,
  PublicAlert,
  PublicFooter,
  PublicGlow,
  PublicScreen,
  PublicShell,
} from "@/components/ui/public-shell";
import { readEnrollmentToken } from "@/lib/auth";
import { getDefaultRoute } from "@/lib/navigation";

const LOGIN_FAILURE_THRESHOLD = 3;
const LOGIN_LOCAL_COOLDOWN_MS = 10_000;
const GENERIC_LOGIN_ERROR = "Unable to sign in with those credentials.";
const LOGIN_TURNSTILE_ERROR = "Complete the verification challenge to continue.";

export default function LoginPage() {
  const router = useRouter();
  const { login, pendingEnrollment, pendingTwoFactor } = useAuth();
  const turnstileSiteKey = process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY?.trim() ?? "";
  const loginTurnstileThreshold = Math.max(
    1,
    Number(process.env.NEXT_PUBLIC_LOGIN_TURNSTILE_THRESHOLD ?? LOGIN_FAILURE_THRESHOLD) || LOGIN_FAILURE_THRESHOLD,
  );
  const isLoginTurnstileAvailable = Boolean(turnstileSiteKey);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [turnstileToken, setTurnstileToken] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [failedAttempts, setFailedAttempts] = useState(0);
  const [cooldownUntil, setCooldownUntil] = useState<number | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const turnstileContainerRef = useRef<HTMLDivElement | null>(null);
  const turnstileWidgetRenderedRef = useRef(false);

  const shouldShowTurnstile = isLoginTurnstileAvailable && failedAttempts >= loginTurnstileThreshold;

  useEffect(() => {
    if (!cooldownUntil) {
      return;
    }

    const intervalId = window.setInterval(() => {
      setNow(Date.now());
    }, 1000);

    return () => window.clearInterval(intervalId);
  }, [cooldownUntil]);

  const cooldownRemainingMs = cooldownUntil ? Math.max(0, cooldownUntil - now) : 0;
  const isCooldownActive = cooldownRemainingMs > 0;
  const cooldownSeconds = Math.ceil(cooldownRemainingMs / 1000);

  useEffect(() => {
    const turnstile = (
      window as Window & {
        turnstile?: {
          render: (
            container: HTMLElement,
            options: {
              sitekey: string;
              callback?: (token: string) => void;
              "expired-callback"?: () => void;
              "error-callback"?: () => void;
            },
          ) => string;
        };
      }
    ).turnstile;

    if (!shouldShowTurnstile || !turnstile || !turnstileContainerRef.current || turnstileWidgetRenderedRef.current) {
      return;
    }

    turnstile.render(turnstileContainerRef.current, {
      sitekey: turnstileSiteKey,
      callback: (token) => {
        setTurnstileToken(token);
      },
      "expired-callback": () => {
        setTurnstileToken("");
      },
      "error-callback": () => {
        setTurnstileToken("");
      },
    });
    turnstileWidgetRenderedRef.current = true;
  }, [shouldShowTurnstile, turnstileSiteKey]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);

    if (isCooldownActive) {
      setError(`Please wait ${cooldownSeconds} seconds before trying again.`);
      return;
    }

    if (shouldShowTurnstile && !turnstileToken) {
      setError(LOGIN_TURNSTILE_ERROR);
      return;
    }

    setIsSubmitting(true);

    try {
      const user = await login({ username, password, turnstile_token: turnstileToken || undefined });
      setFailedAttempts(0);
      setCooldownUntil(null);
      setTurnstileToken("");

      if (!user) {
        if (pendingEnrollment || readEnrollmentToken()) {
          router.replace("/setup-2fa");
          return;
        }
        router.replace("/verify-2fa");
        return;
      }

      const nextRoute = getDefaultRoute(user.role);
      if (nextRoute === "/unauthorized") {
        router.replace("/unauthorized");
        return;
      }

      router.replace(nextRoute);
    } catch (submissionError) {
      const nextFailedAttempts = failedAttempts + 1;
      setFailedAttempts(nextFailedAttempts);

      const message = submissionError instanceof Error ? submissionError.message : GENERIC_LOGIN_ERROR;
      const normalizedMessage = message.toLowerCase();

      if (normalizedMessage.includes("additional verification is required")) {
        setFailedAttempts(Math.max(nextFailedAttempts, loginTurnstileThreshold));
        setError(LOGIN_TURNSTILE_ERROR);
        return;
      }

      if (
        !isLoginTurnstileAvailable &&
        nextFailedAttempts >= LOGIN_FAILURE_THRESHOLD &&
        !normalizedMessage.includes("too many sign-in attempts")
      ) {
        setCooldownUntil(Date.now() + LOGIN_LOCAL_COOLDOWN_MS);
        setNow(Date.now());
        setError(`Please wait ${Math.ceil(LOGIN_LOCAL_COOLDOWN_MS / 1000)} seconds before trying again.`);
        return;
      }

      if (normalizedMessage.includes("too many sign-in attempts")) {
        setError("Too many sign-in attempts. Please wait and try again.");
        return;
      }

      if (isLoginTurnstileAvailable && nextFailedAttempts >= loginTurnstileThreshold) {
        setError(LOGIN_TURNSTILE_ERROR);
        return;
      }

      setError(GENERIC_LOGIN_ERROR);
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <PublicScreen>
      {isLoginTurnstileAvailable ? (
        <Script src="https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit" strategy="afterInteractive" />
      ) : null}
      <PublicGlow side="left" />
      <PublicGlow side="right" />
      <PublicShell narrow>
        <BrandLockup
          image
          subtitle="Climate Health Early Warning System for Cholera Risk Monitoring"
        />

        <div className="w-full max-w-[390px] rounded-[1.75rem] border border-[var(--login-panel-border)] bg-[var(--login-panel-surface)] p-5 shadow-[var(--login-panel-shadow)] backdrop-blur md:max-w-[400px] md:p-6">
          <div className="mb-4 text-center">
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-[var(--login-kicker)]">Authorized System Access</p>
          </div>

          <form className="flex flex-col gap-3" onSubmit={handleSubmit}>
            <InputShell
              id="username"
              label="Username"
              autoComplete="username"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              placeholder="Enter your username"
              icon={<Mail className="size-4" aria-hidden="true" />}
            />

            <PasswordField
              id="password"
              label="Password"
              autoComplete="current-password"
              value={password}
              onChange={setPassword}
              placeholder="Enter your password"
            />

            <p className="text-[11px] leading-snug text-[var(--login-helper)]">For authorized county health officials and CHV coordinators</p>

            {isCooldownActive ? (
              <PublicAlert tone="warning">
                Sign-in is briefly paused in this browser session. Try again in {cooldownSeconds} seconds.
              </PublicAlert>
            ) : null}

            {shouldShowTurnstile ? (
              <div className="rounded-2xl border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] p-4">
                <p className="mb-3 text-sm text-panel-copy">Additional verification is required after repeated sign-in failures.</p>
                <div ref={turnstileContainerRef} />
              </div>
            ) : null}

            {error ? (
              <PublicAlert tone="error">
                <span className="inline-flex items-center gap-2">
                  <ShieldAlert className="size-4" aria-hidden="true" />
                  {error}
                </span>
              </PublicAlert>
            ) : null}

            <Button type="submit" size="lg" disabled={isSubmitting || isCooldownActive} className="mt-1 w-full">
              <KeyRound className="size-4" aria-hidden="true" />
              {isCooldownActive
                ? `Retry in ${cooldownSeconds}s`
                : isSubmitting
                  ? "Signing in..."
                  : "Access System"}
            </Button>
          </form>

          <div className="mt-4 flex items-center justify-between gap-3 text-sm">
            <Link href="/forgot-password" className="text-[var(--login-link)] transition hover:text-[var(--login-link-hover)]">
              Forgot password?
            </Link>
            <Link href="/request-access" className="inline-flex items-center gap-2 text-[var(--login-link)] transition hover:text-[var(--login-link-hover)]">
              Request access
              <ArrowRight className="size-4" aria-hidden="true" />
            </Link>
          </div>
        </div>

        <PublicFooter />
      </PublicShell>
    </PublicScreen>
  );
}
