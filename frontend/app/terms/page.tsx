"use client";

import { ArrowLeft, Download, LayoutGrid, ShieldAlert, Siren, Sparkles } from "lucide-react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  PublicFooter,
  PublicScreen,
  PublicShell,
  PublicTopbar,
} from "@/components/ui/public-shell";
import { StatusBadge } from "@/components/ui/status-badge";

const responsibilityCards = [
  {
    title: "Official purpose",
    copy: "Use the platform only for approved public health monitoring, coordination, research, and operational response work.",
  },
  {
    title: "Security standards",
    copy: "Protect your credentials, maintain device security, and never share access with unauthorized users.",
  },
];

const functionalityCards = [
  { title: "Risk predictions", icon: Sparkles },
  { title: "Automated alerts", icon: Siren },
  { title: "Decision support", icon: LayoutGrid },
];

export default function TermsPage() {
  const router = useRouter();

  return (
    <PublicScreen className="bg-[var(--forgot-background)]">
      <PublicTopbar />
      <PublicShell>
        <div className="w-full space-y-6">
          <div className="space-y-3">
            <div className="flex items-center gap-3">
              <StatusBadge tone="info">Terms</StatusBadge>
              <span className="text-sm font-medium text-panel-muted">Terms of Service</span>
            </div>
            <h1 className="text-5xl font-semibold tracking-tight text-panel-strong">Terms of Service</h1>
            <p className="text-sm text-panel-muted">Last updated: April 2026</p>
          </div>

          <Card className="space-y-8 p-6 md:p-8">
            <article className="space-y-4">
              <h2 className="text-2xl font-semibold text-panel-strong">1. Overview</h2>
              <p className="text-sm leading-7 text-panel-copy">
                The Climate Health Intelligence System (CHIS) is a climate-informed operational platform designed to support public health monitoring, preparedness, and response.
              </p>
              <div className="rounded-2xl border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] px-4 py-3 text-sm text-panel-copy">
                By accessing or using this system, you acknowledge that you have read, understood, and agree to follow these terms.
              </div>
            </article>

            <article className="space-y-4">
              <h2 className="text-2xl font-semibold text-panel-strong">2. Authorized Use</h2>
              <p className="text-sm leading-7 text-panel-copy">Access to CHIS is limited to approved users working in recognized operational roles.</p>
              <div className="flex flex-wrap gap-2">
                {["CHVs and healthcare workers", "County health officials", "Public health officers", "Authorized partners"].map((label) => (
                  <StatusBadge key={label}>{label}</StatusBadge>
                ))}
              </div>
            </article>

            <article className="space-y-4">
              <h2 className="text-2xl font-semibold text-panel-strong">3. User Responsibilities</h2>
              <div className="grid gap-4 md:grid-cols-2">
                {responsibilityCards.map((card) => (
                  <Card key={card.title} className="p-5">
                    <h3 className="text-base font-semibold text-panel-strong">{card.title}</h3>
                    <p className="mt-2 text-sm leading-6 text-panel-copy">{card.copy}</p>
                  </Card>
                ))}
              </div>
            </article>

            <article className="space-y-4">
              <h2 className="text-2xl font-semibold text-panel-strong">4. System Functionality</h2>
              <div className="grid gap-4 sm:grid-cols-3">
                {functionalityCards.map((card) => {
                  const Icon = card.icon;
                  return (
                    <Card key={card.title} className="flex flex-col items-center gap-3 p-5 text-center">
                      <Icon className="size-6 text-brand" aria-hidden="true" />
                      <p className="text-sm font-medium text-panel-copy">{card.title}</p>
                    </Card>
                  );
                })}
              </div>
            </article>

            <article className="space-y-4">
              <h2 className="text-2xl font-semibold text-panel-strong">5. Important Disclaimer</h2>
              <div className="flex items-center gap-3 rounded-2xl border border-[color-mix(in_srgb,var(--warning)_24%,white)] bg-[color-mix(in_srgb,var(--warning)_8%,white)] px-4 py-3 text-sm text-[color:var(--warning)] dark:border-[color-mix(in_srgb,var(--warning)_30%,transparent)] dark:bg-[color-mix(in_srgb,var(--warning)_14%,transparent)] dark:text-[color-mix(in_srgb,var(--warning)_86%,white)]">
                <ShieldAlert className="size-5 shrink-0" aria-hidden="true" />
                <p className="leading-6">
                  CHIS provides operational decision support informed by climate and risk signals. It does not replace professional judgment, official public health procedures, or verified field assessment.
                </p>
              </div>
            </article>

            <div className="grid gap-4 md:grid-cols-2">
              <article className="space-y-3">
                <h2 className="text-2xl font-semibold text-panel-strong">6. System Availability</h2>
                <p className="text-sm leading-7 text-panel-copy">
                  We work to keep the platform available and reliable, but uptime may be affected by maintenance, connectivity, or third-party service interruptions.
                </p>
              </article>
              <article className="space-y-3">
                <h2 className="text-2xl font-semibold text-panel-strong">7. Limitation of Liability</h2>
                <p className="text-sm leading-7 text-panel-copy">
                  CHIS is provided to support public health operations. Users remain responsible for applying appropriate judgment and validating actions in real operational settings.
                </p>
              </article>
            </div>

            <article className="space-y-4">
              <h2 className="text-2xl font-semibold text-panel-strong">8. Administration &amp; Updates</h2>
              <div className="grid gap-4 md:grid-cols-2">
                <Card className="p-5">
                  <h3 className="text-base font-semibold text-panel-strong">Account control</h3>
                  <p className="mt-2 text-sm leading-6 text-panel-copy">Access can be reviewed, limited, or removed when policy or operational requirements change.</p>
                </Card>
                <Card className="p-5">
                  <h3 className="text-base font-semibold text-panel-strong">Terms maintenance</h3>
                  <p className="mt-2 text-sm leading-6 text-panel-copy">These terms may be updated periodically. Material changes will be reflected on this page.</p>
                </Card>
              </div>
            </article>

            <article className="rounded-2xl border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] p-5">
              <h2 className="text-xl font-semibold text-panel-strong">Contact Information</h2>
              <p className="mt-1 text-sm text-panel-copy">For questions regarding these terms or system support.</p>
              <div className="mt-4 grid gap-2 text-sm text-panel-copy">
                <p>Usalama Technology Limited</p>
                <p>support@usalama.tech</p>
              </div>
            </article>
          </Card>

          <div className="flex flex-wrap items-center gap-3">
            <a href="/legal/chis-terms-of-service.pdf" download>
              <Button size="md">
                <Download className="size-4" aria-hidden="true" />
                Download Terms as PDF
              </Button>
            </a>
            <Button type="button" variant="secondary" onClick={() => router.back()}>
              <ArrowLeft className="size-4" aria-hidden="true" />
              Back
            </Button>
          </div>
        </div>

        <PublicFooter />
      </PublicShell>
    </PublicScreen>
  );
}
