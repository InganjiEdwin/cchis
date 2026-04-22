"use client";

import {
  ArrowRight,
  Eye,
  EyeOff,
  KeyRound,
  LockKeyhole,
  Mail,
  ShieldAlert,
} from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import Script from "next/script";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useRef, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { readEnrollmentToken } from "@/lib/auth";
import { getDefaultRoute } from "@/lib/navigation";
import { isDashboardRole } from "@/lib/roles";

const LOGIN_FAILURE_THRESHOLD = 3;
const LOGIN_LOCAL_COOLDOWN_MS = 10_000;
const GENERIC_LOGIN_ERROR = "Unable to sign in with those credentials.";
const LOGIN_TURNSTILE_ERROR = "Complete the verification challenge to continue.";

export default function LoginPage() {
  const router = useRouter();
  const { login, isHydrating, pendingEnrollment, pendingTwoFactor } = useAuth();
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
  const [showPassword, setShowPassword] = useState(false);
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

      if (!isDashboardRole(user.role)) {
        router.replace("/unauthorized");
        return;
      }

      router.replace(getDefaultRoute(user.role));
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
    <div className="login-screen">
      {isLoginTurnstileAvailable ? (
        <Script src="https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit" strategy="afterInteractive" />
      ) : null}

      <div className="login-glow login-glow-left" aria-hidden="true" />
      <div className="login-glow login-glow-right" aria-hidden="true" />

      <main className="login-shell">
        <section className="login-hero">
          <div className="login-brand-mark">
            <Image
              src="/brand/chis-full-colored.png"
              alt="Climate Health Intelligence System"
              width={864}
              height={236}
              priority
              className="login-brand-image"
            />
          </div>
          <p className="login-kicker">Authorized System Access</p>
          <p className="login-description">
            Climate Health Early Warning System for Cholera Risk Monitoring
          </p>
        </section>

        <section className="login-panel">
          <form className="stack" onSubmit={handleSubmit}>
            <div className="login-field">
              <label htmlFor="username">Username</label>
              <div className="login-input-wrap">
                <Mail className="login-input-icon" aria-hidden="true" />
                <input
                  id="username"
                  name="username"
                  autoComplete="username"
                  value={username}
                  onChange={(event) => setUsername(event.target.value)}
                  placeholder="Enter your username"
                  required
                />
              </div>
            </div>

            <div className="login-field">
              <label htmlFor="password">Password</label>
              <div className="login-input-wrap">
                <LockKeyhole className="login-input-icon" aria-hidden="true" />
                <input
                  id="password"
                  name="password"
                  type={showPassword ? "text" : "password"}
                  autoComplete="current-password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  placeholder="Enter your password"
                  required
                />
                <button
                  type="button"
                  className="login-visibility-button"
                  onClick={() => setShowPassword((current) => !current)}
                  aria-label={showPassword ? "Hide password" : "Show password"}
                >
                  {showPassword ? <EyeOff aria-hidden="true" /> : <Eye aria-hidden="true" />}
                </button>
              </div>
            </div>

            <p className="login-helper">For authorized county health officials and CHV coordinators</p>

            {isCooldownActive ? (
              <p className="login-helper">
                Sign-in is briefly paused in this browser session. Try again in {cooldownSeconds} seconds.
              </p>
            ) : null}

            {shouldShowTurnstile ? (
              <>
                <p className="login-helper">Additional verification is required after repeated sign-in failures.</p>
                <div ref={turnstileContainerRef} className="login-turnstile" />
              </>
            ) : null}

            {pendingTwoFactor ? (
              <div className="status status-warning">
                <ShieldAlert className="section-icon" aria-hidden="true" />
                A verification step is still pending for this browser session. Continue to the 2FA code screen
                to finish signing in.
              </div>
            ) : null}

            {pendingEnrollment ? (
              <div className="status status-warning">
                <ShieldAlert className="section-icon" aria-hidden="true" />
                Two-factor setup is still pending for this browser session. Continue to the setup screen to
                complete dashboard access.
              </div>
            ) : null}

            {error ? (
              <div className="status status-error login-error-banner">
                <ShieldAlert className="section-icon" aria-hidden="true" />
                {error}
              </div>
            ) : null}

            <button className="login-submit" type="submit" disabled={isSubmitting || isCooldownActive}>
              <KeyRound className="section-icon login-submit-icon" aria-hidden="true" />
              {isSubmitting ? "Signing in..." : isCooldownActive ? `Retry in ${cooldownSeconds}s` : "Access System"}
            </button>
          </form>

          <div className="login-actions">
            {pendingTwoFactor ? (
              <Link href="/verify-2fa" className="login-link">
                Continue 2FA verification
                <ArrowRight className="section-icon" aria-hidden="true" />
              </Link>
            ) : (
              <Link href="/forgot-password" className="login-link">
                Forgot password?
              </Link>
            )}

            {pendingEnrollment ? (
              <Link href="/setup-2fa" className="login-link">
                Continue 2FA setup
                <ArrowRight className="section-icon" aria-hidden="true" />
              </Link>
            ) : (
              <Link href="/request-access" className="login-link">
                Request access
                <ArrowRight className="section-icon" aria-hidden="true" />
              </Link>
            )}
          </div>
        </section>

        <p className="login-monitoring-note">
          Access monitored for data security and public health system integrity.
        </p>
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
