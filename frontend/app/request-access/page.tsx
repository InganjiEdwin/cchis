"use client";

import { ArrowLeft, ShieldCheck } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import Script from "next/script";
import { useEffect, useMemo, useRef, useState } from "react";

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

  if (!trimmed) {
    return "";
  }

  const compact = trimmed.replace(/[\s()-]+/g, "");

  if (/^\+254\d{9}$/.test(compact)) {
    return compact;
  }

  if (/^254\d{9}$/.test(compact)) {
    return `+${compact}`;
  }

  if (/^0\d{9}$/.test(compact)) {
    return `+254${compact.slice(1)}`;
  }

  return compact;
}

function isValidKenyanPhoneNumber(value: string) {
  return value === "" || /^\+254\d{9}$/.test(value);
}

function validateRequestForm(form: FormState, visibleWards: Array<{ id: number; name: string }>): FormErrors {
  const errors: FormErrors = {};

  if (!form.full_name.trim()) {
    errors.full_name = "Full name is required.";
  }

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

  if (!form.desired_role) {
    errors.desired_role = "Select a role.";
  }

  if (!form.county) {
    errors.county = "Select a county.";
  }

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
    if (!counties.length) {
      return;
    }

    setForm((current) => {
      if (current.county) {
        return current;
      }

      return {
        ...current,
        county: counties[0],
      };
    });
  }, [counties]);

  const visibleWards = useMemo(() => {
    if (!form.county) {
      return wards;
    }
    return wards.filter((ward) => ward.county === form.county);
  }, [form.county, wards]);

  useEffect(() => {
    if (!visibleWards.length) {
      return;
    }

    setForm((current) => {
      if (current.administrative_ward && visibleWards.some((ward) => ward.name === current.administrative_ward)) {
        return current;
      }

      return {
        ...current,
        administrative_ward: visibleWards[0].name,
      };
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

    if (!turnstile || !turnstileContainerRef.current || turnstileWidgetRenderedRef.current) {
      return;
    }

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

  return (
    <div className="access-request-screen">
      <header className="request-topbar">
        <Link href="/login" className="request-brand">
          <Image
            src="/brand/chis-brief-colored.png"
            alt=""
            width={96}
            height={96}
            aria-hidden="true"
            className="request-brand-mark"
          />
          <span>CHIS</span>
        </Link>
        <div className="request-topbar-actions">
          <Link href="/login" className="request-topbar-link">
            <ArrowLeft aria-hidden="true" />
            Back to Login
          </Link>
        </div>
      </header>

      {isTurnstileEnabled ? (
        <Script src="https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit" strategy="afterInteractive" />
      ) : null}

      <main className="request-shell">
        <section className="request-hero">
          <h1 className="request-title">Request Access</h1>
          <p className="request-subtitle">Submit your details for review by the system administrator.</p>
        </section>

        <section className="request-card">
          <form className="stack" onSubmit={handleSubmit}>
            <div className="request-honeypot" aria-hidden="true">
              <label htmlFor="website">Website</label>
              <input
                id="website"
                tabIndex={-1}
                autoComplete="off"
                value={form.website}
                onChange={(event) => setForm((current) => ({ ...current, website: event.target.value }))}
              />
            </div>

            <div className="request-grid">
              <div className="login-field">
                <label htmlFor="full_name">Full Name</label>
                <div className="login-input-wrap request-input-wrap">
                  <input
                    id="full_name"
                    value={form.full_name}
                    onChange={(event) => {
                      const value = event.target.value;
                      setForm((current) => ({ ...current, full_name: value }));
                      setFieldErrors((current) => ({ ...current, full_name: undefined }));
                    }}
                    placeholder="e.g. Dr. Jane Doe"
                    required
                    aria-invalid={Boolean(fieldErrors.full_name)}
                    aria-describedby={fieldErrors.full_name ? "full_name-error" : undefined}
                  />
                </div>
                {fieldErrors.full_name ? (
                  <p id="full_name-error" className="request-field-error">
                    {fieldErrors.full_name}
                  </p>
                ) : null}
              </div>

              <div className="login-field">
                <label htmlFor="contact_email">Email Address</label>
                <div className="login-input-wrap request-input-wrap">
                  <input
                    id="contact_email"
                    type="email"
                    value={form.contact_email}
                    onChange={(event) => {
                      const value = event.target.value;
                      setForm((current) => ({ ...current, contact_email: value }));
                      setFieldErrors((current) => ({ ...current, contact_email: undefined }));
                    }}
                    placeholder="name@organization.go.ke"
                    required
                    aria-invalid={Boolean(fieldErrors.contact_email)}
                    aria-describedby={fieldErrors.contact_email ? "contact_email-error" : undefined}
                  />
                </div>
                {fieldErrors.contact_email ? (
                  <p id="contact_email-error" className="request-field-error">
                    {fieldErrors.contact_email}
                  </p>
                ) : null}
              </div>

              <div className="login-field">
                <label htmlFor="phone_number">Phone Number</label>
                <div className="login-input-wrap request-input-wrap">
                  <input
                    id="phone_number"
                    type="tel"
                    inputMode="tel"
                    value={form.phone_number}
                    onChange={(event) => {
                      const value = event.target.value;
                      setForm((current) => ({ ...current, phone_number: value }));
                      setFieldErrors((current) => ({ ...current, phone_number: undefined }));
                    }}
                    placeholder="e.g. +254711000123 or 0711000123"
                    aria-invalid={Boolean(fieldErrors.phone_number)}
                    aria-describedby={fieldErrors.phone_number ? "phone_number-error" : undefined}
                  />
                </div>
                {fieldErrors.phone_number ? (
                  <p id="phone_number-error" className="request-field-error">
                    {fieldErrors.phone_number}
                  </p>
                ) : null}
              </div>

              <div className="login-field">
                <label htmlFor="desired_role">Role</label>
                <div className="request-select-wrap">
                  <select
                    id="desired_role"
                    value={form.desired_role}
                    onChange={(event) => {
                      const value = event.target.value as UserRole | "";
                      setForm((current) => ({ ...current, desired_role: value }));
                      setFieldErrors((current) => ({ ...current, desired_role: undefined }));
                    }}
                    required
                    aria-invalid={Boolean(fieldErrors.desired_role)}
                    aria-describedby={fieldErrors.desired_role ? "desired_role-error" : undefined}
                  >
                    <option value="">Select Role</option>
                    {ROLE_OPTIONS.map((role) => (
                      <option key={role.value} value={role.value}>
                        {role.label}
                      </option>
                    ))}
                  </select>
                </div>
                {fieldErrors.desired_role ? (
                  <p id="desired_role-error" className="request-field-error">
                    {fieldErrors.desired_role}
                  </p>
                ) : null}
              </div>

              <div className="login-field">
                <label htmlFor="county">County</label>
                <div className="request-select-wrap">
                  <select
                    id="county"
                    value={form.county}
                    onChange={(event) => {
                      const value = event.target.value;
                      setForm((current) => ({
                        ...current,
                        county: value,
                      }));
                      setFieldErrors((current) => ({
                        ...current,
                        county: undefined,
                        administrative_ward: undefined,
                      }));
                    }}
                    required
                    disabled={isLoadingOptions || !counties.length}
                    aria-invalid={Boolean(fieldErrors.county)}
                    aria-describedby={fieldErrors.county ? "county-error" : undefined}
                  >
                    <option value="">Select County</option>
                    {counties.map((county) => (
                      <option key={county} value={county}>
                        {county}
                      </option>
                    ))}
                  </select>
                </div>
                {fieldErrors.county ? (
                  <p id="county-error" className="request-field-error">
                    {fieldErrors.county}
                  </p>
                ) : null}
              </div>

              <div className="login-field">
                <label htmlFor="administrative_ward">Administrative Ward</label>
                <div className="request-select-wrap">
                  <select
                    id="administrative_ward"
                    value={form.administrative_ward}
                    onChange={(event) => {
                      const value = event.target.value;
                      setForm((current) => ({ ...current, administrative_ward: value }));
                      setFieldErrors((current) => ({ ...current, administrative_ward: undefined }));
                    }}
                    required
                    disabled={isLoadingOptions || !visibleWards.length}
                    aria-invalid={Boolean(fieldErrors.administrative_ward)}
                    aria-describedby={fieldErrors.administrative_ward ? "administrative_ward-error" : undefined}
                  >
                    <option value="">{isLoadingOptions ? "Loading wards..." : "Select ward"}</option>
                    {visibleWards.map((ward) => (
                      <option key={ward.id} value={ward.name}>
                        {ward.name}
                      </option>
                    ))}
                  </select>
                </div>
                {fieldErrors.administrative_ward ? (
                  <p id="administrative_ward-error" className="request-field-error">
                    {fieldErrors.administrative_ward}
                  </p>
                ) : null}
              </div>
            </div>

            <div className="login-field">
              <label htmlFor="organization">
                Organization or Facility <span className="request-optional">(Optional)</span>
              </label>
              <div className="login-input-wrap request-input-wrap">
                <input
                  id="organization"
                  value={form.organization}
                  onChange={(event) => setForm((current) => ({ ...current, organization: event.target.value }))}
                  placeholder="Health Center or Organization Name"
                />
              </div>
            </div>

            <div className="login-field">
              <label htmlFor="message">
                Reason for Access <span className="request-optional">(Optional)</span>
              </label>
              <textarea
                id="message"
                className="request-textarea"
                value={form.message}
                onChange={(event) => setForm((current) => ({ ...current, message: event.target.value }))}
                placeholder="Tell us why you need access and how you will use the system..."
                rows={5}
              />
            </div>

            {error ? <div className="status status-error login-error-banner">{error}</div> : null}
            {successMessage ? <div className="status request-success-banner">{successMessage}</div> : null}
            {isTurnstileEnabled ? <div ref={turnstileContainerRef} className="request-turnstile" /> : null}

            <button className="request-submit" type="submit" disabled={isSubmitting || isLoadingOptions}>
              {isSubmitting ? "Submitting..." : "Submit Request"}
            </button>

            <Link href="/login" className="request-back-link">
              <ArrowLeft className="section-icon" aria-hidden="true" />
              Back to Login
            </Link>
          </form>
        </section>

        <section className="request-support-grid">
          <article className="request-support-card">
            <ShieldCheck className="section-icon" aria-hidden="true" />
            <div>
              <h3>Secure</h3>
              <p>Your details are protected and used only to review your access request.</p>
            </div>
          </article>
          <article className="request-support-card">
            <ShieldCheck className="section-icon" aria-hidden="true" />
            <div>
              <h3>Reviewed</h3>
              <p>Requests are reviewed by the system administrator before access is granted.</p>
            </div>
          </article>
          <article className="request-support-card">
            <ShieldCheck className="section-icon" aria-hidden="true" />
            <div>
              <h3>Support</h3>
              <p>Select the role and location that best match how you will use the system.</p>
            </div>
          </article>
        </section>
      </main>

      <footer className="login-footer request-footer">
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
