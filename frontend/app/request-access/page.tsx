"use client";

import { ArrowLeft, ShieldCheck } from "lucide-react";
import Link from "next/link";
import Script from "next/script";
import { useEffect, useMemo, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { InputShell } from "@/components/ui/input-shell";
import {
  PublicAlert,
  PublicCard,
  PublicFooter,
  PublicScreen,
  PublicShell,
  PublicTopbar,
} from "@/components/ui/public-shell";
import { fetchAccessRequestOptions, submitAccessRequest, type UserRole } from "@/lib/auth";

type FormState = {
  full_name: string;
  contact_email: string;
  phone_number: string;
  desired_role: UserRole | "";
  county: string;
  administrative_ward: string;
  organization: string;
  message: string;
  website: string;
  turnstile_token: string;
};

type FormErrors = Partial<Record<keyof FormState, string>>;

const ROLE_OPTIONS: Array<{ value: UserRole; label: string }> = [
  { value: "ADMIN", label: "Administrator" },
  { value: "SUPERVISOR", label: "Supervisor" },
  { value: "ANALYST", label: "Analyst" },
  { value: "CHV", label: "CHV" },
];

function normalizeKenyanPhoneNumber(value: string) {
  const trimmed = value.trim();
  if (!trimmed) return "";
  const compact = trimmed.replace(/[\s()-]+/g, "");
  if (/^\+254\d{9}$/.test(compact)) return compact;
  if (/^254\d{9}$/.test(compact)) return `+${compact}`;
  if (/^0\d{9}$/.test(compact)) return `+254${compact.slice(1)}`;
  return compact;
}

function isValidKenyanPhoneNumber(value: string) {
  return value === "" || /^\+254\d{9}$/.test(value);
}

function validateRequestForm(form: FormState, visibleWards: Array<{ id: number; name: string }>): FormErrors {
  const errors: FormErrors = {};
  if (!form.full_name.trim()) errors.full_name = "Full name is required.";
  const normalizedEmail = form.contact_email.trim();
  if (!normalizedEmail) {
    errors.contact_email = "Email address is required.";
  } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(normalizedEmail)) {
    errors.contact_email = "Enter a valid email address.";
  }
  const normalizedPhoneNumber = normalizeKenyanPhoneNumber(form.phone_number);
  if (form.phone_number.trim() && !isValidKenyanPhoneNumber(normalizedPhoneNumber)) {
    errors.phone_number = "Use +254711000123, 254711000123, or 0711000123.";
  }
  if (!form.desired_role) errors.desired_role = "Select a role.";
  if (!form.county) errors.county = "Select a county.";
  if (!form.administrative_ward) {
    errors.administrative_ward = "Select an administrative ward.";
  } else if (!visibleWards.some((ward) => ward.name === form.administrative_ward)) {
    errors.administrative_ward = "Select a ward that belongs to the chosen county.";
  }
  return errors;
}

export default function RequestAccessPage() {
  const turnstileSiteKey = process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY?.trim() ?? "";
  const isTurnstileEnabled = Boolean(turnstileSiteKey);
  const [form, setForm] = useState<FormState>({
    full_name: "",
    contact_email: "",
    phone_number: "",
    desired_role: "",
    county: "",
    administrative_ward: "",
    organization: "",
    message: "",
    website: "",
    turnstile_token: "",
  });
  const [counties, setCounties] = useState<string[]>([]);
  const [wards, setWards] = useState<Array<{ id: number; name: string; county: string; sub_county: string }>>([]);
  const [isLoadingOptions, setIsLoadingOptions] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<FormErrors>({});
  const startedAtRef = useRef(Date.now());
  const turnstileContainerRef = useRef<HTMLDivElement | null>(null);
  const turnstileWidgetRenderedRef = useRef(false);

  useEffect(() => {
    const load = async () => {
      try {
        const response = await fetchAccessRequestOptions();
        setCounties(response.counties);
        setWards(response.wards);
      } catch (loadError) {
        setError(loadError instanceof Error ? loadError.message : "Unable to load request options.");
      } finally {
        setIsLoadingOptions(false);
      }
    };

    void load();
  }, []);

  useEffect(() => {
    if (!counties.length) return;
    setForm((current) => (current.county ? current : { ...current, county: counties[0] }));
  }, [counties]);

  const visibleWards = useMemo(() => (!form.county ? wards : wards.filter((ward) => ward.county === form.county)), [form.county, wards]);

  useEffect(() => {
    if (!visibleWards.length) return;
    setForm((current) => {
      if (current.administrative_ward && visibleWards.some((ward) => ward.name === current.administrative_ward)) {
        return current;
      }
      return { ...current, administrative_ward: visibleWards[0].name };
    });
  }, [visibleWards]);

  useEffect(() => {
    if (!isTurnstileEnabled || typeof window === "undefined") {
      return;
    }

    const turnstile = (
      window as Window & {
        turnstile?: {
          render: (
            element: HTMLElement,
            options: {
              sitekey: string;
              callback: (token: string) => void;
              "expired-callback": () => void;
              "error-callback": () => void;
            },
          ) => string;
        };
      }
    ).turnstile;

    if (!turnstile || !turnstileContainerRef.current || turnstileWidgetRenderedRef.current) return;

    turnstile.render(turnstileContainerRef.current, {
      sitekey: turnstileSiteKey,
      callback: (token: string) => {
        setForm((current) => ({ ...current, turnstile_token: token }));
        setError(null);
      },
      "expired-callback": () => {
        setForm((current) => ({ ...current, turnstile_token: "" }));
      },
      "error-callback": () => {
        setForm((current) => ({ ...current, turnstile_token: "" }));
      },
    });
    turnstileWidgetRenderedRef.current = true;
  }, [isTurnstileEnabled, turnstileSiteKey]);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSuccessMessage(null);

    if (isTurnstileEnabled && !form.turnstile_token) {
      setError("Complete the challenge before submitting your request.");
      return;
    }

    const nextFieldErrors = validateRequestForm(form, visibleWards);
    if (Object.keys(nextFieldErrors).length) {
      setFieldErrors(nextFieldErrors);
      return;
    }

    setFieldErrors({});
    setIsSubmitting(true);

    try {
      const normalizedPhoneNumber = normalizeKenyanPhoneNumber(form.phone_number);

      const response = await submitAccessRequest({
        full_name: form.full_name,
        phone_number: normalizedPhoneNumber,
        county: form.county,
        administrative_ward: form.administrative_ward,
        organization: form.organization,
        desired_role: form.desired_role as UserRole,
        contact_email: form.contact_email,
        message: form.message,
        website: form.website,
        client_started_at_ms: startedAtRef.current,
        turnstile_token: form.turnstile_token,
      });
      setSuccessMessage(response.detail);
      setForm((current) => ({
        ...current,
        full_name: "",
        contact_email: "",
        phone_number: "",
        desired_role: "",
        administrative_ward: "",
        organization: "",
        message: "",
        website: "",
        turnstile_token: "",
      }));
      setFieldErrors({});
      startedAtRef.current = Date.now();
    } catch (submissionError) {
      setError(
        submissionError instanceof Error ? submissionError.message : "Unable to submit your request right now.",
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  const selectClasses = "h-11 rounded-pill border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] px-4 text-sm text-panel-strong outline-none focus:border-[var(--dashboard-icon-button-border)]";
  const fieldLabel = "text-sm font-medium text-panel-copy";

  return (
    <PublicScreen className="bg-[var(--request-background)]">
      {isTurnstileEnabled ? (
        <Script src="https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit" strategy="afterInteractive" />
      ) : null}
      <PublicTopbar showHelp />
      <PublicShell className="items-stretch">
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1.2fr)_minmax(280px,0.8fr)]">
          <PublicCard>
            <div className="mb-6">
              <h1 className="text-4xl font-semibold tracking-tight text-[var(--request-title)]">Request Dashboard Access</h1>
              <p className="mt-2 text-sm text-[var(--request-subtitle)]">
                Submit your operational details to request access to the CHIS dashboard.
              </p>
            </div>

            <form className="space-y-4" onSubmit={handleSubmit}>
              <div className="grid gap-4 md:grid-cols-2">
                <InputShell
                  id="full_name"
                  label="Full Name"
                  value={form.full_name}
                  onChange={(event) => setForm((current) => ({ ...current, full_name: event.target.value }))}
                  placeholder="Your full name"
                />
                <InputShell
                  id="contact_email"
                  label="Email Address"
                  type="email"
                  value={form.contact_email}
                  onChange={(event) => setForm((current) => ({ ...current, contact_email: event.target.value }))}
                  placeholder="name@example.org"
                />
              </div>

              <div className="grid gap-4 md:grid-cols-2">
                <InputShell
                  id="phone_number"
                  label="Phone Number"
                  value={form.phone_number}
                  onChange={(event) => setForm((current) => ({ ...current, phone_number: event.target.value }))}
                  placeholder="+254711000123"
                />
                <label className="flex flex-col gap-2">
                  <span className={fieldLabel}>Role</span>
                  <select
                    aria-label="Role"
                    className={selectClasses}
                    value={form.desired_role}
                    onChange={(event) => setForm((current) => ({ ...current, desired_role: event.target.value as UserRole | "" }))}
                  >
                    <option value="">Select role</option>
                    {ROLE_OPTIONS.map((role) => (
                      <option key={role.value} value={role.value}>
                        {role.label}
                      </option>
                    ))}
                  </select>
                </label>
              </div>

              <div className="grid gap-4 md:grid-cols-2">
                <label className="flex flex-col gap-2">
                  <span className={fieldLabel}>County</span>
                  <select
                    aria-label="County"
                    className={selectClasses}
                    value={form.county}
                    onChange={(event) => setForm((current) => ({ ...current, county: event.target.value }))}
                    disabled={isLoadingOptions}
                  >
                    {counties.map((county) => (
                      <option key={county} value={county}>
                        {county}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="flex flex-col gap-2">
                  <span className={fieldLabel}>Administrative Ward</span>
                  <select
                    aria-label="Administrative Ward"
                    className={selectClasses}
                    value={form.administrative_ward}
                    onChange={(event) => setForm((current) => ({ ...current, administrative_ward: event.target.value }))}
                    disabled={isLoadingOptions}
                  >
                    {visibleWards.map((ward) => (
                      <option key={ward.id} value={ward.name}>
                        {ward.name}
                      </option>
                    ))}
                  </select>
                </label>
              </div>

              <InputShell
                id="organization"
                label="Organization or Facility"
                value={form.organization}
                onChange={(event) => setForm((current) => ({ ...current, organization: event.target.value }))}
                placeholder="County health department"
              />

              <label className="flex flex-col gap-2">
                <span className={fieldLabel}>Reason for Access</span>
                <textarea
                  aria-label="Reason for Access"
                  className="min-h-28 rounded-[1.5rem] border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] px-4 py-3 text-sm text-panel-strong outline-none placeholder:text-panel-subtle focus:border-[var(--dashboard-icon-button-border)]"
                  value={form.message}
                  onChange={(event) => setForm((current) => ({ ...current, message: event.target.value }))}
                  placeholder="Tell us briefly why you need access."
                />
              </label>

              <input
                type="text"
                value={form.website}
                onChange={(event) => setForm((current) => ({ ...current, website: event.target.value }))}
                autoComplete="off"
                tabIndex={-1}
                className="hidden"
                aria-hidden="true"
              />

              {Object.values(fieldErrors).length ? (
                <PublicAlert tone="warning">
                  {Object.values(fieldErrors)[0]}
                </PublicAlert>
              ) : null}
              {error ? <PublicAlert tone="error">{error}</PublicAlert> : null}
              {successMessage ? <PublicAlert tone="success">{successMessage}</PublicAlert> : null}

              {isTurnstileEnabled ? <div ref={turnstileContainerRef} className="pt-1" /> : null}

              <Button className="w-full" size="lg" type="submit" disabled={isSubmitting || isLoadingOptions}>
                {isSubmitting ? "Submitting request..." : "Submit Request"}
              </Button>
            </form>
          </PublicCard>

          <PublicCard className="self-start">
            <div className="mb-5 flex items-center gap-3">
              <span className="inline-flex size-11 items-center justify-center rounded-2xl bg-[color-mix(in_srgb,var(--dashboard-sidebar-title)_14%,white)] text-brand">
                <ShieldCheck className="size-5" aria-hidden="true" />
              </span>
              <div>
                <h2 className="text-xl font-semibold text-panel-strong">Access Guidelines</h2>
                <p className="text-sm text-panel-muted">Requests are reviewed against operational need and role scope.</p>
              </div>
            </div>

            <ul className="space-y-3 text-sm text-panel-copy">
              <li>Use an official email where possible.</li>
              <li>Select the role that best reflects your real operational responsibility.</li>
              <li>Choose the ward you primarily support so access can be scoped correctly.</li>
              <li>CHIS access is role-based and may require two-factor enrollment after approval.</li>
            </ul>

            <div className="mt-6">
              <Link href="/login" className="inline-flex items-center gap-2 text-sm font-medium text-brand transition hover:text-[var(--login-link-hover)]">
                <ArrowLeft className="size-4" aria-hidden="true" />
                Back to Login
              </Link>
            </div>
          </PublicCard>
        </div>

        <PublicFooter />
      </PublicShell>
    </PublicScreen>
  );
}
