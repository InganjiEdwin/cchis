"use client";

import {
  BadgeCheck,
  Brush,
  KeyRound,
  LogOut,
  MapPinned,
  ShieldCheck,
  UserRound,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { PageFrame } from "@/components/page-frame";
import { useAuth } from "@/components/auth-provider";

export default function ProfilePage() {
  const router = useRouter();
  const { currentUser, logout, updateAppearance } = useAuth();
  const [isSigningOut, setIsSigningOut] = useState(false);
  const [isSavingAppearance, setIsSavingAppearance] = useState(false);
  const [appearanceError, setAppearanceError] = useState<string | null>(null);

  if (!currentUser) {
    return null;
  }

  const displayName = currentUser.full_name || currentUser.username;
  const scopeLabel =
    currentUser.scope_type === "WARD"
      ? currentUser.ward_name || "Ward-scoped access"
      : currentUser.scope_type === "BROAD"
        ? "County-wide access"
        : currentUser.ward_name || "No explicit scope assigned";
  const twoFactorLabel =
    currentUser.two_factor_policy === "REQUIRED"
      ? currentUser.is_totp_enabled
        ? "Required and enabled"
        : "Required but not enrolled"
      : currentUser.two_factor_policy === "OPTIONAL"
        ? currentUser.is_totp_enabled
          ? "Optional and enabled"
        : "Optional and not enabled"
      : "Not required for this role";
  const appearanceOptions = [
    { value: "SYSTEM", label: "System" },
    { value: "LIGHT", label: "Light" },
    { value: "DARK", label: "Dark" },
  ] as const;

  async function handleSignOut() {
    setIsSigningOut(true);

    try {
      await logout();
      router.replace("/login");
    } finally {
      setIsSigningOut(false);
    }
  }

  async function handleAppearanceChange(themePreference: "SYSTEM" | "LIGHT" | "DARK") {
    setAppearanceError(null);
    setIsSavingAppearance(true);

    try {
      await updateAppearance(themePreference);
    } catch (error) {
      setAppearanceError(
        error instanceof Error ? error.message : "Unable to save your appearance preference right now.",
      );
    } finally {
      setIsSavingAppearance(false);
    }
  }

  return (
    <PageFrame
      title="Profile"
      summary="A session-aware account surface for confirming role, scope, and current sign-in security before deeper account-management features are added."
      role={currentUser.role}
    >
      <section className="page-grid metrics-2">
        <article className="card">
          <div className="card-header">
            <UserRound className="section-icon" aria-hidden="true" />
            <h3>Identity</h3>
          </div>
          <p className="muted">
            This page confirms the active account details loaded through the authenticated session.
          </p>
          <dl className="detail-list">
            <div>
              <dt>Display name</dt>
              <dd>{displayName}</dd>
            </div>
            <div>
              <dt>Username</dt>
              <dd>{currentUser.username}</dd>
            </div>
            <div>
              <dt>Email</dt>
              <dd>{currentUser.email || "Not provided"}</dd>
            </div>
            <div>
              <dt>Phone number</dt>
              <dd>{currentUser.phone_number || "Not provided"}</dd>
            </div>
          </dl>
        </article>
        <article className="card">
          <div className="card-header">
            <BadgeCheck className="section-icon" aria-hidden="true" />
            <h3>Scope</h3>
          </div>
          <p className="muted">
            Role and scope come from `/api/v1/auth/me/` and should match backend-enforced access.
          </p>
          <dl className="detail-list">
            <div>
              <dt>Role</dt>
              <dd>{currentUser.role}</dd>
            </div>
            <div>
              <dt>Scope type</dt>
              <dd>{currentUser.scope_type || "Not specified"}</dd>
            </div>
            <div>
              <dt>Assigned ward</dt>
              <dd>{currentUser.ward_name || "County-wide or unassigned"}</dd>
            </div>
            <div>
              <dt>Account active</dt>
              <dd>{currentUser.is_active ? "Yes" : "No"}</dd>
            </div>
          </dl>
        </article>
      </section>

      <section className="page-grid metrics-2">
        <article className="card">
          <div className="card-header">
            <ShieldCheck className="section-icon" aria-hidden="true" />
            <h3>Security</h3>
          </div>
          <div className="stack">
            <div className="status">
              <KeyRound className="section-icon" aria-hidden="true" />
              Two-factor status: {twoFactorLabel}
            </div>
            <dl className="detail-list">
              <div>
                <dt>2FA policy</dt>
                <dd>{currentUser.two_factor_policy || "Not exposed"}</dd>
              </div>
              <div>
                <dt>TOTP enrolled</dt>
                <dd>{currentUser.is_totp_enabled ? "Yes" : "No"}</dd>
              </div>
            </dl>
            <p className="muted">
              Use the setup flow here to enroll TOTP when your role policy requires or allows it.
            </p>
            {currentUser.two_factor_policy !== "NONE" && !currentUser.is_totp_enabled ? (
              <div className="inline-actions">
                <Link href="/setup-2fa" className="button button-secondary">
                  <KeyRound className="section-icon" aria-hidden="true" />
                  Set up TOTP
                </Link>
              </div>
            ) : null}
          </div>
        </article>

        <article className="card">
          <div className="card-header">
            <Brush className="section-icon" aria-hidden="true" />
            <h3>Appearance</h3>
          </div>
          <div className="stack">
            <p className="muted">
              By default the dashboard follows your device theme. Save an override here if you always want
              light or dark mode when this account signs in.
            </p>
            <div className="field">
              <label htmlFor="theme-preference">Theme preference</label>
              <select
                id="theme-preference"
                value={currentUser.theme_preference}
                onChange={(event) => {
                  void handleAppearanceChange(event.target.value as "SYSTEM" | "LIGHT" | "DARK");
                }}
                disabled={isSavingAppearance}
              >
                {appearanceOptions.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="status">
              <Brush className="section-icon" aria-hidden="true" />
              Active preference:{" "}
              {currentUser.theme_preference === "SYSTEM"
                ? "Following your device setting"
                : `${currentUser.theme_preference.toLowerCase()} mode`}
            </div>
            {appearanceError ? <div className="status status-error">{appearanceError}</div> : null}
            {isSavingAppearance ? <p className="muted">Saving appearance preference...</p> : null}
          </div>
        </article>

        <article className="card">
          <div className="card-header">
            <MapPinned className="section-icon" aria-hidden="true" />
            <h3>Operational context</h3>
          </div>
          <div className="stack">
            <div className="status">
              <MapPinned className="section-icon" aria-hidden="true" />
              Current access scope: {scopeLabel}
            </div>
            <p className="muted">
              Use this view to sanity-check that the dashboard is rendering the expected role and scope before
              taking operational actions elsewhere.
            </p>
          </div>
        </article>
      </section>

      <section className="page-grid">
        <article className="card">
          <div className="card-header">
            <LogOut className="section-icon" aria-hidden="true" />
            <h3>Session actions</h3>
          </div>
          <p className="muted">
            Sign out here when handing off the device or ending your current dashboard session.
          </p>
          <div className="inline-actions" style={{ marginTop: "1rem" }}>
            <button
              type="button"
              className="button button-secondary"
              onClick={() => {
                void handleSignOut();
              }}
              disabled={isSigningOut}
            >
              <LogOut className="section-icon" aria-hidden="true" />
              {isSigningOut ? "Signing out..." : "Sign out"}
            </button>
          </div>
        </article>
      </section>
    </PageFrame>
  );
}
