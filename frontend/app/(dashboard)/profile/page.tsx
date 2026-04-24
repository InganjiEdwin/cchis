"use client";

import { ChevronRight, Clock3, Globe, KeyRound, LogOut, MapPinned, MonitorCog, RefreshCcw, ShieldCheck, Smartphone, UserRound } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { DashboardTopbar } from "@/components/dashboard-topbar";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { StatusBanner } from "@/components/ui/status-banner";
import { StatusBadge } from "@/components/ui/status-badge";
import { cn } from "@/lib/cn";

function getInitials(name: string) {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part.charAt(0).toUpperCase())
    .join("");
}

function buildCapabilityCopy(role: string) {
  if (role === "ADMIN") {
    return {
      heading: "This section offers broad role notes only.",
      items: [
        "View alert, ward, CHV, facility, and system summary pages available to your role.",
        "Access on-page actions only where a real route is exposed in the dashboard.",
        "Use linked pages to review recorded or calculated operational context.",
        "Treat this card as role notes, not a full route list.",
      ],
      note: "Role notes only",
    };
  }

  if (role === "ANALYST") {
    return {
      heading: "This section offers broad role notes only.",
      items: [
        "View alert, ward, CHV, facility, and system summary pages available to your role.",
        "Access on-page actions only where a real route is exposed in the dashboard.",
        "Use linked pages to review recorded or calculated operational context.",
        "Treat this card as role notes, not a full route list.",
      ],
      note: "Role notes only",
    };
  }

  if (role === "SUPERVISOR") {
    return {
      heading: "This section offers broad role notes only.",
      items: [
        "View alert, ward, CHV, facility, and system summary pages available to your role.",
        "Access on-page actions only where a real route is exposed in the dashboard.",
        "Use linked pages to review recorded or calculated operational context.",
        "Treat this card as role notes, not a full route list.",
      ],
      note: "Role notes only",
    };
  }

  return {
    heading: "This section offers broad role notes only.",
    items: [
      "View alert, ward, CHV, facility, and system summary pages available to your role.",
      "Access on-page actions only where a real route is exposed in the dashboard.",
      "Use linked pages to review recorded or calculated operational context.",
      "Treat this card as role notes, not a full route list.",
    ],
    note: "Role notes only",
  };
}

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
  const initials = getInitials(displayName || currentUser.username);
  const scopeLabel =
    currentUser.scope_type === "WARD"
      ? currentUser.ward_name || "Ward-scoped access"
      : currentUser.scope_type === "BROAD"
        ? "Migori County"
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
  const capabilityCopy = buildCapabilityCopy(currentUser.role);
  const detailItems = [
    { label: "Email address", value: currentUser.email || "Not provided" },
    { label: "Phone number", value: currentUser.phone_number || "Not provided" },
    { label: "Organization", value: "No organization record exposed on this page" },
    { label: "Account record", value: "No account-created timestamp exposed on this page" },
  ];

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
    <div className="space-y-6">
      <DashboardTopbar
        title="Profile"
        subtitle="Identity, role, and access summary"
        lastUpdatedLabel="Profile shown"
      />

      {appearanceError ? (
        <StatusBanner tone="danger">{appearanceError}</StatusBanner>
      ) : null}

      <section className="grid gap-6 xl:grid-cols-[minmax(0,1.55fr)_20rem]">
        <Card className="rounded-[2rem] px-6 py-6">
          <div className="flex flex-col gap-6 md:flex-row md:items-start md:justify-between">
            <div className="flex items-start gap-4">
              <div className="relative">
                <div className="flex size-[5.9rem] items-center justify-center rounded-[1.45rem] bg-[linear-gradient(180deg,#2d7f89_0%,#1d5375_100%)] text-[1.7rem] font-semibold tracking-[-0.04em] text-white shadow-[0_20px_36px_rgba(27,79,115,0.24)]">
                  {initials}
                </div>
                <span className="absolute -bottom-1.5 -right-1.5 inline-flex size-7 items-center justify-center rounded-full bg-brand text-white shadow-[0_10px_18px_rgba(23,95,194,0.24)]">
                  <UserRound className="size-3.5" aria-hidden="true" />
                </span>
              </div>

              <div className="space-y-4">
                <div>
                  <div className="flex flex-wrap items-center gap-3">
                    <h2 className="text-[1.85rem] font-semibold tracking-[-0.05em] text-panel-strong">
                      {displayName}
                    </h2>
                    <StatusBadge tone="info" className="px-3 py-1 tracking-[0.14em]">
                      {currentUser.role.replaceAll("_", " ")}
                    </StatusBadge>
                  </div>
                  <p className="mt-1 text-sm font-medium text-panel-muted">
                    Role from session
                  </p>
                </div>

                <div className="space-y-2 text-sm text-panel-copy">
                  <div className="flex items-center gap-2">
                    <MapPinned className="size-4 text-brand" aria-hidden="true" />
                    <span>{scopeLabel}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <ShieldCheck className="size-4 text-brand" aria-hidden="true" />
                    <span>Dashboard profile page</span>
                  </div>
                </div>

                <div className="inline-flex items-center gap-2 rounded-pill border border-panel-table-wrap bg-[color-mix(in_srgb,var(--dashboard-table-line)_24%,transparent)] px-3 py-1.5 text-xs font-semibold uppercase tracking-[0.14em] text-panel-copy">
                  <Clock3 className="size-3.5" aria-hidden="true" />
                  Profile shown
                </div>
              </div>
            </div>

            <div className="flex w-full flex-col gap-3 md:w-auto md:min-w-[15rem]">
              <div className="rounded-[1.35rem] border border-panel-table-wrap bg-[color-mix(in_srgb,var(--dashboard-table-line)_18%,transparent)] px-4 py-4">
                <p className="text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle">
                  Two-factor
                </p>
                <div className="mt-2 flex items-center justify-between gap-3">
                  <span className="text-sm font-medium text-panel-copy">Two-factor</span>
                  <StatusBadge
                    tone={
                      currentUser.two_factor_policy === "NONE"
                        ? "default"
                        : currentUser.is_totp_enabled
                          ? "success"
                          : "warning"
                    }
                    className="px-3 py-1 tracking-[0.14em]"
                  >
                    {currentUser.is_totp_enabled ? "Enabled" : currentUser.two_factor_policy === "NONE" ? "None" : "Action needed"}
                  </StatusBadge>
                </div>
              </div>

              <div className="flex flex-wrap items-center gap-3">
                {currentUser.two_factor_policy !== "NONE" && !currentUser.is_totp_enabled ? (
                  <Link
                    href="/setup-2fa"
                    className="inline-flex h-11 items-center justify-center gap-2 rounded-pill border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] px-4 text-sm font-semibold text-panel-copy transition hover:border-[var(--dashboard-icon-button-border)] hover:text-panel-strong"
                  >
                    <KeyRound className="size-4" aria-hidden="true" />
                    Set up TOTP
                  </Link>
                ) : null}

                <Button
                  variant="secondary"
                  onClick={() => {
                    void handleSignOut();
                  }}
                  disabled={isSigningOut}
                >
                  <LogOut className="size-4" aria-hidden="true" />
                  {isSigningOut ? "Signing out..." : "Sign out"}
                </Button>
              </div>
            </div>
          </div>
        </Card>

        <Card className="rounded-[2rem] border-none bg-[linear-gradient(180deg,#165fbe_0%,#0f56b0_100%)] px-5 py-5 text-white shadow-[0_20px_40px_rgba(15,86,176,0.28)]">
            <div className="space-y-4">
              <div>
                <p className="text-[0.72rem] font-semibold uppercase tracking-[0.18em] text-white/68">
                  Role Notes
                </p>
              <p className="mt-2 text-sm text-white/80">This card shows role notes only. Approval and report routes are unavailable.</p>
              </div>

              <div className="rounded-[1.25rem] border border-white/12 bg-white/10 px-4 py-4">
                <div className="flex items-center justify-between gap-3">
                <span className="text-sm font-medium text-white/84">Role</span>
                <span className="text-xl font-semibold">{currentUser.role.replaceAll("_", " ")}</span>
                </div>
              </div>

              <div className="rounded-[1.1rem] border border-white/10 bg-black/10 px-4 py-3 text-sm text-white/78">
              Text on this page comes from visible session data.
              </div>

            <Button className="w-full bg-white/18 text-white shadow-none hover:bg-white/18" disabled>
              Report generation unavailable
            </Button>
          </div>
        </Card>
      </section>

      <section className="grid gap-6 xl:grid-cols-[minmax(0,1.55fr)_20rem]">
        <Card className="rounded-[2rem] px-6 py-6">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h2 className="text-[1.25rem] font-semibold tracking-[-0.04em] text-panel-strong">Account Details</h2>
              <p className="mt-1 text-sm text-panel-muted">Identity fields and preferences shown here.</p>
            </div>
            <button
              type="button"
              disabled
              className="inline-flex items-center gap-2 text-sm font-semibold text-brand transition hover:text-[var(--dashboard-icon-button-ink-hover)]"
            >
              Update unavailable
            </button>
          </div>

          <div className="mt-6 grid gap-3 sm:grid-cols-2">
            {detailItems.map((item) => (
              <div
                key={item.label}
                className="rounded-[1.2rem] border border-panel-table-wrap bg-[color-mix(in_srgb,var(--dashboard-table-line)_20%,transparent)] px-4 py-4"
              >
                <p className="text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle">
                  {item.label}
                </p>
                <p className="mt-2 text-sm font-semibold text-panel-strong">{item.value}</p>
              </div>
            ))}
          </div>

          <div className="mt-6 border-t border-[var(--dashboard-table-line)] pt-6">
            <p className="text-[0.68rem] font-semibold uppercase tracking-[0.18em] text-panel-subtle">Preferences</p>
            <div className="mt-4 grid gap-3 md:grid-cols-2">
              <div className="flex items-center justify-between rounded-[1.25rem] border border-panel-table-wrap bg-[color-mix(in_srgb,var(--dashboard-table-line)_24%,transparent)] px-4 py-3 opacity-75">
                <span className="flex items-center gap-3">
                  <Globe className="size-4 text-panel-muted" aria-hidden="true" />
                  <span className="text-sm font-medium text-panel-copy">Alert notifications</span>
                </span>
                <span className="inline-flex h-6 w-11 items-center rounded-full bg-[color-mix(in_srgb,var(--dashboard-table-line)_65%,transparent)] px-1">
                  <span className="ml-auto size-4 rounded-full bg-white" />
                </span>
              </div>

              <label className="flex items-center justify-between rounded-[1.25rem] border border-panel-table-wrap bg-[color-mix(in_srgb,var(--dashboard-table-line)_24%,transparent)] px-4 py-3">
                <span className="flex items-center gap-3">
                  <MonitorCog className="size-4 text-panel-muted" aria-hidden="true" />
                  <span className="text-sm font-medium text-panel-copy">Appearance</span>
                </span>
                <select
                  value={currentUser.theme_preference}
                  onChange={(event) => {
                    void handleAppearanceChange(event.target.value as "SYSTEM" | "LIGHT" | "DARK");
                  }}
                  disabled={isSavingAppearance}
                  className="min-w-[8rem] bg-transparent text-right text-sm font-medium text-panel-strong outline-none"
                >
                  {appearanceOptions.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            <p className="mt-3 text-sm text-panel-muted">
              Alert-notification preferences are not exposed as a saved setting on this page yet.
            </p>

            {isSavingAppearance ? (
              <p className="mt-3 text-sm text-panel-muted">Saving appearance preference...</p>
            ) : null}
          </div>
        </Card>

        <Card className="rounded-[2rem] px-5 py-6">
          <div>
            <h2 className="text-[1.25rem] font-semibold tracking-[-0.04em] text-panel-strong">Role Notes</h2>
            <p className="mt-2 text-sm leading-6 text-panel-muted">{capabilityCopy.heading}</p>
          </div>

          <div className="mt-5 space-y-4">
            {capabilityCopy.items.map((item) => (
              <div key={item} className="flex items-start gap-3">
                <span className="mt-1 inline-flex size-6 items-center justify-center rounded-full bg-[color-mix(in_srgb,var(--brand)_12%,white)] text-brand dark:bg-[color-mix(in_srgb,var(--brand)_18%,transparent)]">
                  <ChevronRight className="size-3.5" aria-hidden="true" />
                </span>
                <p className="text-sm leading-6 text-panel-copy">{item}</p>
              </div>
            ))}
          </div>

          <div className="mt-6 rounded-[1.2rem] border border-panel-table-wrap bg-[color-mix(in_srgb,var(--dashboard-table-line)_28%,transparent)] px-4 py-3">
            <div className="flex items-center gap-3">
              <span className="inline-flex size-8 items-center justify-center rounded-xl bg-[color-mix(in_srgb,var(--brand)_12%,white)] text-brand dark:bg-[color-mix(in_srgb,var(--brand)_18%,transparent)]">
                <ShieldCheck className="size-4" aria-hidden="true" />
              </span>
              <span className="text-sm font-medium text-panel-copy">{capabilityCopy.note}</span>
            </div>
          </div>
        </Card>
      </section>

      <section className="grid gap-6">
        <Card className="rounded-[2rem] px-6 py-6">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h2 className="text-[1.25rem] font-semibold tracking-[-0.04em] text-panel-strong">
                Security & Authentication
              </h2>
              <p className="mt-1 text-sm text-panel-muted">Credential, second-factor, and session details shown here.</p>
            </div>
          </div>

          <div className="mt-6 grid gap-4 lg:grid-cols-3">
            <Card className="rounded-[1.5rem] bg-[color-mix(in_srgb,var(--dashboard-table-line)_20%,transparent)] px-5 py-5 shadow-none">
              <div className="flex items-center gap-3">
                <span className="inline-flex size-10 items-center justify-center rounded-2xl bg-[color-mix(in_srgb,var(--brand)_12%,white)] text-brand dark:bg-[color-mix(in_srgb,var(--brand)_18%,transparent)]">
                  <KeyRound className="size-4" aria-hidden="true" />
                </span>
                <strong className="text-base font-semibold text-panel-strong">Password</strong>
              </div>
              <p className="mt-4 min-h-[4.5rem] text-sm leading-6 text-panel-muted">
                Password-change timing is not exposed on this page.
              </p>
              <button
                type="button"
                disabled
                className="mt-5 inline-flex items-center gap-2 text-sm font-semibold text-brand transition hover:text-[var(--dashboard-icon-button-ink-hover)]"
              >
                Password change unavailable
                <ChevronRight className="size-4" aria-hidden="true" />
              </button>
            </Card>

            <Card className="rounded-[1.5rem] bg-[color-mix(in_srgb,var(--dashboard-table-line)_20%,transparent)] px-5 py-5 shadow-none">
              <div className="flex items-center gap-3">
                <span className="inline-flex size-10 items-center justify-center rounded-2xl bg-[color-mix(in_srgb,var(--warning)_14%,white)] text-[color:var(--warning)] dark:bg-[color-mix(in_srgb,var(--warning)_20%,transparent)]">
                  <ShieldCheck className="size-4" aria-hidden="true" />
                </span>
                <strong className="text-base font-semibold text-panel-strong">Two-Factor (2FA)</strong>
              </div>
              <p className="mt-4 min-h-[4.5rem] text-sm leading-6 text-panel-muted">
                TOTP setup is available on this page. Visible state: {twoFactorLabel}.
              </p>
              <Link
                href="/setup-2fa"
                className="mt-5 inline-flex items-center gap-2 text-sm font-semibold text-brand transition hover:text-[var(--dashboard-icon-button-ink-hover)]"
              >
                Manage TOTP
                <ChevronRight className="size-4" aria-hidden="true" />
              </Link>
            </Card>

            <Card className="rounded-[1.5rem] bg-[color-mix(in_srgb,var(--dashboard-table-line)_20%,transparent)] px-5 py-5 shadow-none">
              <div className="flex items-center gap-3">
                <span className="inline-flex size-10 items-center justify-center rounded-2xl bg-[color-mix(in_srgb,var(--success)_14%,white)] text-[color:var(--success)] dark:bg-[color-mix(in_srgb,var(--success)_20%,transparent)]">
                  <Smartphone className="size-4" aria-hidden="true" />
                </span>
                <strong className="text-base font-semibold text-panel-strong">Session Summary</strong>
              </div>
              <p className="mt-4 min-h-[4.5rem] text-sm leading-6 text-panel-muted">
                Device count and session-location details are not exposed on this page.
              </p>
              <button
                type="button"
                disabled
                className="mt-5 inline-flex items-center gap-2 text-sm font-semibold text-brand transition hover:text-[var(--dashboard-icon-button-ink-hover)]"
              >
                Session review unavailable
                <ChevronRight className="size-4" aria-hidden="true" />
              </button>
            </Card>
          </div>
        </Card>
      </section>

      <section className="grid gap-6">
        <Card className="rounded-[2rem] px-6 py-6">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h2 className="text-[1.25rem] font-semibold tracking-[-0.04em] text-panel-strong">Recent Activity Log</h2>
              <p className="mt-1 text-sm text-panel-muted">Account activity is not exposed on this page yet.</p>
            </div>
            <button
              type="button"
              disabled
              className="text-[0.72rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle transition hover:text-panel-copy"
            >
              Audit trail unavailable
            </button>
          </div>

          <div className="mt-6 rounded-[1.35rem] border border-panel-table-wrap px-4 py-5 text-sm text-panel-muted">
            No account activity records are exposed on this page yet.
          </div>

          <div className="mt-5 flex flex-wrap items-center gap-4 text-sm text-panel-muted">
            <span className="inline-flex items-center gap-2">
              <RefreshCcw className="size-4" aria-hidden="true" />
              Profile data shown here
            </span>
            <span className="inline-flex items-center gap-2">
              <ShieldCheck className="size-4" aria-hidden="true" />
              Account status: {currentUser.is_active ? "Active" : "Inactive"}
            </span>
            <span className="inline-flex items-center gap-2">
              <MapPinned className="size-4" aria-hidden="true" />
              Scope: {scopeLabel}
            </span>
          </div>
        </Card>
      </section>
    </div>
  );
}
