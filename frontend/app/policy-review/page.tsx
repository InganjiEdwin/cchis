"use client";

import { Suspense, useEffect, useMemo, useState, type FormEvent } from "react";
import { CheckCircle2, FileText, LogOut, ShieldCheck, ShieldAlert } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";

import { useAuth } from "@/components/auth-provider";
import { Button } from "@/components/ui/button";
import {
  BrandLockup,
  PublicAlert,
  PublicCard,
  PublicFooter,
  PublicGlow,
  PublicScreen,
  PublicShell,
} from "@/components/ui/public-shell";
import { fetchPolicyAcceptanceViaBff, requiresPolicyAcceptance, type PolicyAcceptanceState } from "@/lib/auth";
import { getDefaultRoute, getSafePolicyReturnTo } from "@/lib/navigation";

export default function PolicyReviewPage() {
  return (
    <Suspense fallback={<PolicyReviewFallback />}>
      <PolicyReviewPageContent />
    </Suspense>
  );
}

function PolicyReviewFallback() {
  return (
    <PublicScreen>
      <PublicGlow side="left" />
      <PublicGlow side="right" />
      <PublicShell narrow className="justify-center">
        <PublicCard className="max-w-[640px]">
          <p className="text-sm text-panel-copy">Preparing policy review...</p>
        </PublicCard>
      </PublicShell>
    </PublicScreen>
  );
}

function PolicyReviewPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const {
    acceptPolicies,
    currentUser,
    isAuthenticated,
    isHydrating,
    logout,
  } = useAuth();
  const defaultRoute = currentUser ? getDefaultRoute(currentUser) : "/overview";
  const returnTo = useMemo(
    () => getSafePolicyReturnTo(searchParams.get("returnTo"), defaultRoute === "/unauthorized" ? "/unauthorized" : defaultRoute),
    [defaultRoute, searchParams],
  );
  const [fetchedPolicyAcceptance, setFetchedPolicyAcceptance] = useState<PolicyAcceptanceState | null>(null);
  const [acceptedTerms, setAcceptedTerms] = useState(false);
  const [acceptedPrivacy, setAcceptedPrivacy] = useState(false);
  const [acceptedCookieNotice, setAcceptedCookieNotice] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isLoadingPolicy, setIsLoadingPolicy] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const policyAcceptance = currentUser?.policy_acceptance ?? fetchedPolicyAcceptance;
  const isReadyToAccept = acceptedTerms && acceptedPrivacy && acceptedCookieNotice && Boolean(policyAcceptance) && !isSubmitting;

  useEffect(() => {
    if (isHydrating) {
      return;
    }

    if (!isAuthenticated || !currentUser) {
      router.replace("/login");
      return;
    }

    if (currentUser.policy_acceptance) {
      return;
    }

    let isActive = true;

    async function loadPolicyAcceptance() {
      setIsLoadingPolicy(true);
      setError(null);

      try {
        const policyState = await fetchPolicyAcceptanceViaBff();
        if (isActive) {
          setFetchedPolicyAcceptance(policyState);
        }
      } catch (loadError) {
        if (isActive) {
          setError(
            loadError instanceof Error
              ? loadError.message
              : "Unable to load the current policy versions.",
          );
        }
      } finally {
        if (isActive) {
          setIsLoadingPolicy(false);
        }
      }
    }

    void loadPolicyAcceptance();

    return () => {
      isActive = false;
    };
  }, [currentUser, isAuthenticated, isHydrating, router]);

  useEffect(() => {
    if (isHydrating || !currentUser || !policyAcceptance) {
      return;
    }

    if (!requiresPolicyAcceptance({ ...currentUser, policy_acceptance: policyAcceptance })) {
      router.replace(returnTo);
    }
  }, [currentUser, isHydrating, policyAcceptance, returnTo, router]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);

    if (!policyAcceptance) {
      setError("Policy versions are still loading. Please try again in a moment.");
      return;
    }

    if (!acceptedTerms || !acceptedPrivacy || !acceptedCookieNotice) {
      setError("Accept the Terms of Service and acknowledge the Privacy Policy and Cookie Notice to continue.");
      return;
    }

    setIsSubmitting(true);

    try {
      await acceptPolicies({
        accepted_terms: acceptedTerms,
        accepted_privacy: acceptedPrivacy,
        accepted_cookie_notice: acceptedCookieNotice,
        terms_version: policyAcceptance.terms_version,
        privacy_version: policyAcceptance.privacy_version,
        cookie_notice_version: policyAcceptance.cookie_notice_version,
      });
      router.replace(returnTo);
    } catch (submissionError) {
      setError(
        submissionError instanceof Error
          ? submissionError.message
          : "Unable to record policy acceptance. Please try again.",
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleSignOut() {
    await logout();
    router.replace("/login");
  }

  const hasAcceptedPreviousVersion = Boolean(
    policyAcceptance?.accepted_terms_version ||
      policyAcceptance?.accepted_privacy_version ||
      policyAcceptance?.accepted_cookie_notice_version,
  );
  const title = hasAcceptedPreviousVersion ? "CHIS policies have been updated" : "Before you continue";
  const canShowForm = Boolean(currentUser && policyAcceptance && requiresPolicyAcceptance({ ...currentUser, policy_acceptance: policyAcceptance }));

  return (
    <PublicScreen>
      <PublicGlow side="left" />
      <PublicGlow side="right" />
      <PublicShell narrow className="justify-center">
        <BrandLockup image subtitle="Climate Health Early Warning System for Cholera Risk Monitoring" />

        <PublicCard className="max-w-[680px]">
          <div className="mb-6 flex items-start gap-4">
            <span className="inline-flex size-12 shrink-0 items-center justify-center rounded-2xl bg-[color-mix(in_srgb,var(--dashboard-sidebar-title)_14%,white)] text-brand">
              <ShieldCheck className="size-6" aria-hidden="true" />
            </span>
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[var(--login-kicker)]">
                Policy Review
              </p>
              <h1 className="mt-2 text-4xl font-semibold leading-tight text-[var(--totp-ink)]">{title}</h1>
              <p className="mt-3 text-sm leading-6 text-panel-copy">
                Please review and accept the current CHIS Terms of Service and Privacy Policy. These explain how CHIS supports public health operations, how account data is handled, and your responsibility to protect system access.
              </p>
            </div>
          </div>

          {isHydrating || isLoadingPolicy ? (
            <PublicAlert>Loading current policy requirements...</PublicAlert>
          ) : null}

          {error ? (
            <div className="mt-4">
              <PublicAlert tone="error">
                <span className="inline-flex items-center gap-2">
                  <ShieldAlert className="size-4" aria-hidden="true" />
                  {error}
                </span>
              </PublicAlert>
            </div>
          ) : null}

          {policyAcceptance ? (
            <div className="mt-5 grid gap-3 rounded-[1.25rem] border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] p-4 text-sm text-panel-copy sm:grid-cols-3">
              <div>
                <p className="font-semibold text-panel-strong">Terms</p>
                <p className="mt-1">{policyAcceptance.terms_version}</p>
              </div>
              <div>
                <p className="font-semibold text-panel-strong">Privacy</p>
                <p className="mt-1">{policyAcceptance.privacy_version}</p>
              </div>
              <div>
                <p className="font-semibold text-panel-strong">Cookie Notice</p>
                <p className="mt-1">{policyAcceptance.cookie_notice_version}</p>
              </div>
            </div>
          ) : null}

          {policyAcceptance && canShowForm ? (
            <form className="mt-6 flex flex-col gap-4" onSubmit={handleSubmit}>
              <label className="flex items-start gap-3 rounded-[1rem] border border-panel-table-wrap bg-[color-mix(in_srgb,var(--dashboard-table-line)_18%,transparent)] px-4 py-3 text-sm font-medium text-panel-copy">
                <input
                  type="checkbox"
                  checked={acceptedTerms}
                  onChange={(event) => setAcceptedTerms(event.target.checked)}
                  className="mt-1 size-4 accent-[var(--login-submit-start)]"
                />
                I have read and agree to the Terms of Service.
              </label>

              <label className="flex items-start gap-3 rounded-[1rem] border border-panel-table-wrap bg-[color-mix(in_srgb,var(--dashboard-table-line)_18%,transparent)] px-4 py-3 text-sm font-medium text-panel-copy">
                <input
                  type="checkbox"
                  checked={acceptedPrivacy}
                  onChange={(event) => setAcceptedPrivacy(event.target.checked)}
                  className="mt-1 size-4 accent-[var(--login-submit-start)]"
                />
                I have read and acknowledge the Privacy Policy.
              </label>

              <label className="flex items-start gap-3 rounded-[1rem] border border-panel-table-wrap bg-[color-mix(in_srgb,var(--dashboard-table-line)_18%,transparent)] px-4 py-3 text-sm font-medium text-panel-copy">
                <input
                  type="checkbox"
                  checked={acceptedCookieNotice}
                  onChange={(event) => setAcceptedCookieNotice(event.target.checked)}
                  className="mt-1 size-4 accent-[var(--login-submit-start)]"
                />
                I acknowledge the current Cookie Notice.
              </label>

              <div className="grid gap-3 lg:grid-cols-3">
                <Link href={policyAcceptance.terms_url} className="inline-flex h-11 items-center justify-center gap-2 rounded-pill border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] px-4 text-sm font-semibold text-panel-copy transition hover:border-[var(--dashboard-icon-button-border)] hover:text-panel-strong">
                  <FileText className="size-4" aria-hidden="true" />
                  Read Terms
                </Link>
                <Link href={policyAcceptance.privacy_url} className="inline-flex h-11 items-center justify-center gap-2 rounded-pill border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] px-4 text-sm font-semibold text-panel-copy transition hover:border-[var(--dashboard-icon-button-border)] hover:text-panel-strong">
                  <FileText className="size-4" aria-hidden="true" />
                  Read Privacy Policy
                </Link>
                <Link href={policyAcceptance.cookie_notice_url} className="inline-flex h-11 items-center justify-center gap-2 rounded-pill border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] px-4 text-sm font-semibold text-panel-copy transition hover:border-[var(--dashboard-icon-button-border)] hover:text-panel-strong">
                  <FileText className="size-4" aria-hidden="true" />
                  Read Cookie Notice
                </Link>
              </div>

              <Button type="submit" size="lg" disabled={!isReadyToAccept} className="w-full">
                <CheckCircle2 className="size-4" aria-hidden="true" />
                {isSubmitting ? "Recording acceptance..." : "Accept and continue"}
              </Button>
            </form>
          ) : null}

          <div className="mt-5 flex justify-center">
            <button
              type="button"
              onClick={() => void handleSignOut()}
              className="inline-flex items-center gap-2 text-sm font-medium text-[var(--totp-link-muted)] transition hover:text-[var(--totp-link)]"
            >
              <LogOut className="size-4" aria-hidden="true" />
              Sign out
            </button>
          </div>
        </PublicCard>

        <PublicFooter />
      </PublicShell>
    </PublicScreen>
  );
}
