"use client";

import {
  BellRing,
  ChevronRight,
  Clock3,
  Globe,
  KeyRound,
  LogOut,
  MapPinned,
  MonitorCog,
  RefreshCcw,
  ShieldCheck,
  Smartphone,
  UserRound,
  Waves,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { DashboardTopbar } from "@/components/dashboard-topbar";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { StatusBanner } from "@/components/ui/status-banner";
import { StatusBadge } from "@/components/ui/status-badge";
import { cn } from "@/lib/cn";

function formatDisplayDate(timestamp: Date) {
  return timestamp.toLocaleDateString([], {
    month: "long",
    day: "numeric",
    year: "numeric",
  });
}

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
      heading: "Your role grants full administrative control over the Migori regional intelligence node.",
      items: [
        "View real-time alerts and climate-health trend triggers.",
        "Manage CHVs, assign monitors, and audit community-health volunteers.",
        "Trigger protocols and adjust threshold rules for operational response.",
        "Modify regional thresholds and coordination settings.",
      ],
      trust: "Trust level: Tier 4 Administrator",
      approvals: 12,
    };
  }

  if (role === "ANALYST") {
    return {
      heading: "Your role focuses on analysis, quality review, and coordination support.",
      items: [
        "Review real-time alerts and risk model output.",
        "Export reports and investigate regional readiness trends.",
        "Support escalation reviews and audit event trails.",
        "Recommend protocol changes for admin approval.",
      ],
      trust: "Trust level: Tier 3 Analyst",
      approvals: 4,
    };
  }

  if (role === "SUPERVISOR") {
    return {
      heading: "Your role oversees sub-county coordination and operational readiness.",
      items: [
        "Monitor visible alerts and local field conditions.",
        "Coordinate CHV activity and ward-level follow-up.",
        "Review readiness gaps and dispatch recommendations.",
        "Escalate critical incidents to county administrators.",
      ],
      trust: "Trust level: Tier 2 Supervisor",
      approvals: 3,
    };
  }

  return {
    heading: "Your role provides field visibility and operational follow-up.",
    items: [
      "View assigned alerts and local readiness signals.",
      "Submit field updates and community observations.",
      "Receive dispatch and escalation instructions.",
      "Support follow-up workflows from the dashboard.",
    ],
    trust: "Trust level: Tier 1 Field Operator",
    approvals: 1,
  };
}

export default function ProfilePage() {
  const router = useRouter();
  const { currentUser, logout, updateAppearance } = useAuth();
  const [isSigningOut, setIsSigningOut] = useState(false);
  const [isSavingAppearance, setIsSavingAppearance] = useState(false);
  const [appearanceError, setAppearanceError] = useState<string | null>(null);

  const now = useMemo(() => new Date(), []);

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
  const accountCreatedLabel = formatDisplayDate(new Date(now.getFullYear(), 0, 12));
  const activityItems = [
    {
      title: "Triggered Flood Protocol - Sector B",
      subtitle: "Emergency alert dispatched to 42 CHVs",
      time: "Today, 09:02 AM",
      tone: "info" as const,
      icon: Waves,
    },
    {
      title: "Exported Health Risk Report",
      subtitle: "PDF generated for County Health Board",
      time: "Yesterday, 04:30 PM",
      tone: "default" as const,
      icon: Globe,
    },
    {
      title: "Updated Risk Thresholds",
      subtitle: "Changed AQI alert level for pediatric respiratory units",
      time: "Oct 14, 11:05 AM",
      tone: "warning" as const,
      icon: MonitorCog,
    },
  ];
  const detailItems = [
    { label: "Email address", value: currentUser.email || "Not provided" },
    { label: "Phone number", value: currentUser.phone_number || "Not provided" },
    { label: "Organization", value: "Migori County Government" },
    { label: "Account created", value: accountCreatedLabel },
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
        subtitle="Account identity, permissions, and security overview"
        lastUpdatedLabel="Profile sync active"
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
                    Lead Epidemiologist & Health Informatics Officer
                  </p>
                </div>

                <div className="space-y-2 text-sm text-panel-copy">
                  <div className="flex items-center gap-2">
                    <MapPinned className="size-4 text-brand" aria-hidden="true" />
                    <span>{scopeLabel}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <ShieldCheck className="size-4 text-brand" aria-hidden="true" />
                    <span>Migori County Health Directorate</span>
                  </div>
                </div>

                <div className="inline-flex items-center gap-2 rounded-pill border border-panel-table-wrap bg-[color-mix(in_srgb,var(--dashboard-table-line)_24%,transparent)] px-3 py-1.5 text-xs font-semibold uppercase tracking-[0.14em] text-panel-copy">
                  <Clock3 className="size-3.5" aria-hidden="true" />
                  Profile synced to active session
                </div>
              </div>
            </div>

            <div className="flex w-full flex-col gap-3 md:w-auto md:min-w-[15rem]">
              <div className="rounded-[1.35rem] border border-panel-table-wrap bg-[color-mix(in_srgb,var(--dashboard-table-line)_18%,transparent)] px-4 py-4">
                <p className="text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle">
                  Account readiness
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
                System Health Status
              </p>
              <p className="mt-2 text-sm text-white/80">Your administrative oversight is active.</p>
            </div>

            <div className="rounded-[1.25rem] border border-white/12 bg-white/10 px-4 py-4">
              <div className="flex items-center justify-between gap-3">
                <span className="text-sm font-medium text-white/84">Pending approvals</span>
                <span className="text-xl font-semibold">{capabilityCopy.approvals}</span>
              </div>
            </div>

            <div className="rounded-[1.1rem] border border-white/10 bg-black/10 px-4 py-3 text-sm text-white/78">
              Trust posture verified for current administrative session.
            </div>

            <Button className="w-full bg-white text-[#175fc2] shadow-none hover:bg-white/92">
              Generate Report
            </Button>
          </div>
        </Card>
      </section>

      <section className="grid gap-6 xl:grid-cols-[minmax(0,1.55fr)_20rem]">
        <Card className="rounded-[2rem] px-6 py-6">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h2 className="text-[1.25rem] font-semibold tracking-[-0.04em] text-panel-strong">Account Details</h2>
              <p className="mt-1 text-sm text-panel-muted">Primary identity and preference settings for this session.</p>
            </div>
            <button
              type="button"
              className="inline-flex items-center gap-2 text-sm font-semibold text-brand transition hover:text-[var(--dashboard-icon-button-ink-hover)]"
            >
              Update
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
              <div className="flex items-center justify-between rounded-[1.25rem] border border-panel-table-wrap bg-[color-mix(in_srgb,var(--dashboard-table-line)_24%,transparent)] px-4 py-3">
                <span className="flex items-center gap-3">
                  <BellRing className="size-4 text-panel-muted" aria-hidden="true" />
                  <span className="text-sm font-medium text-panel-copy">Alert notifications</span>
                </span>
                <span className="inline-flex h-6 w-11 items-center rounded-full bg-brand px-1">
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

            {isSavingAppearance ? (
              <p className="mt-3 text-sm text-panel-muted">Saving appearance preference...</p>
            ) : null}
          </div>
        </Card>

        <Card className="rounded-[2rem] px-5 py-6">
          <div>
            <h2 className="text-[1.25rem] font-semibold tracking-[-0.04em] text-panel-strong">Capabilities</h2>
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
              <span className="text-sm font-medium text-panel-copy">{capabilityCopy.trust}</span>
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
              <p className="mt-1 text-sm text-panel-muted">Credential, second-factor, and session readiness controls.</p>
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
                Last changed 4 months ago. We recommend updating your password every 6 months.
              </p>
              <button
                type="button"
                className="mt-5 inline-flex items-center gap-2 text-sm font-semibold text-brand transition hover:text-[var(--dashboard-icon-button-ink-hover)]"
              >
                Change Password
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
                Secure your account with TOTP authenticator access. Current state: {twoFactorLabel}.
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
                <strong className="text-base font-semibold text-panel-strong">Active Sessions</strong>
              </div>
              <p className="mt-4 min-h-[4.5rem] text-sm leading-6 text-panel-muted">
                2 devices currently logged in. Your current session is from Nairobi, Kenya.
              </p>
              <button
                type="button"
                className="mt-5 inline-flex items-center gap-2 text-sm font-semibold text-brand transition hover:text-[var(--dashboard-icon-button-ink-hover)]"
              >
                Review Sessions
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
              <p className="mt-1 text-sm text-panel-muted">Latest operator actions associated with your account.</p>
            </div>
            <button
              type="button"
              className="text-[0.72rem] font-semibold uppercase tracking-[0.16em] text-panel-subtle transition hover:text-panel-copy"
            >
              View full audit trail
            </button>
          </div>

          <div className="mt-6 space-y-3">
            {activityItems.map((item) => {
              const Icon = item.icon;

              return (
                <div
                  key={item.title}
                  className="flex flex-col gap-3 rounded-[1.35rem] border border-panel-table-wrap px-4 py-4 sm:flex-row sm:items-center sm:justify-between"
                >
                  <div className="flex items-start gap-3">
                    <span
                      className={cn(
                        "inline-flex size-9 items-center justify-center rounded-full",
                        item.tone === "info" &&
                          "bg-[color-mix(in_srgb,var(--brand)_12%,white)] text-brand dark:bg-[color-mix(in_srgb,var(--brand)_18%,transparent)]",
                        item.tone === "warning" &&
                          "bg-[color-mix(in_srgb,var(--warning)_14%,white)] text-[color:var(--warning)] dark:bg-[color-mix(in_srgb,var(--warning)_20%,transparent)]",
                        item.tone === "default" &&
                          "bg-[color-mix(in_srgb,var(--dashboard-table-line)_60%,transparent)] text-panel-copy",
                      )}
                    >
                      <Icon className="size-4" aria-hidden="true" />
                    </span>
                    <div>
                      <strong className="block text-sm font-semibold text-panel-strong">{item.title}</strong>
                      <p className="mt-1 text-xs text-panel-muted">{item.subtitle}</p>
                    </div>
                  </div>

                  <div className="inline-flex items-center gap-2 text-xs font-medium uppercase tracking-[0.14em] text-panel-subtle">
                    <Clock3 className="size-3.5" aria-hidden="true" />
                    {item.time}
                  </div>
                </div>
              );
            })}
          </div>

          <div className="mt-5 flex flex-wrap items-center gap-4 text-sm text-panel-muted">
            <span className="inline-flex items-center gap-2">
              <RefreshCcw className="size-4" aria-hidden="true" />
              Session-backed profile data
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
