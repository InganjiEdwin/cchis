"use client";

import {
  ArrowLeft,
  DatabaseZap,
  Download,
  LockKeyhole,
  Radar,
  Share2,
  Siren,
} from "lucide-react";
import Link from "next/link";
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

const sections = [
  {
    title: "1. Introduction",
    body: [
      "The Climate Health Intelligence System (CHIS) supports climate-informed public health monitoring and response. Our privacy mission is to protect access to system information while giving authorized teams the visibility they need to coordinate risk response and operational follow-through.",
    ],
  },
  {
    title: "2. Information We Collect",
    cards: [
      {
        title: "User information",
        copy: "Names, email addresses, phone numbers, user role, county, and organization details used for account access and operations.",
      },
      {
        title: "System data",
        copy: "Security events, login activity, and interaction metadata used to maintain system integrity and investigate misuse.",
      },
      {
        title: "Environmental and health data",
        copy: "Climate, rainfall, risk, and operational records used to support planning, monitoring, and coordinated response.",
      },
    ],
    note: "CHIS does not collect, store, or process individual patient health records as part of routine system use.",
  },
  {
    title: "3. How We Use Data",
    bullets: [
      {
        icon: Radar,
        copy: "To generate and distribute climate-health risk insights to authorized users.",
      },
      {
        icon: Siren,
        copy: "To coordinate monitoring, alerts, and operational decision support.",
      },
      {
        icon: LockKeyhole,
        copy: "To secure the platform and limit access to authorized public health stakeholders.",
      },
    ],
  },
  {
    title: "4. Data Sharing",
    body: [
      "We share system information only with authorized operational stakeholders and approved partners when needed to support public health monitoring, response coordination, and system administration.",
    ],
    callout: "CHIS access is role-based and limited to users whose work requires visibility into the system.",
  },
  {
    title: "5. Data Security",
    body: [
      "We apply security safeguards including strong authentication, audit logging, role-based access control, and other protective controls appropriate for a climate-health operations platform.",
    ],
  },
  {
    title: "6. Data Retention",
    body: [
      "System information is retained only as long as required for operations, accountability, and reporting needs, and is reviewed periodically against administrative requirements.",
    ],
  },
  {
    title: "7. User Responsibilities",
    body: [
      "Authorized users are responsible for protecting their credentials, respecting role boundaries, and reporting any suspected misuse or unauthorized access immediately.",
    ],
  },
];

export default function PrivacyPage() {
  const router = useRouter();

  return (
    <PublicScreen className="bg-[var(--forgot-background)]">
      <PublicTopbar />
      <PublicShell>
        <div className="w-full space-y-6">
          <div className="space-y-3">
            <div className="flex items-center gap-3">
              <StatusBadge tone="info">Official Policy</StatusBadge>
              <span className="text-sm font-medium text-panel-muted">Privacy Policy</span>
            </div>
            <h1 className="text-5xl font-semibold tracking-tight text-panel-strong">Privacy Policy</h1>
            <p className="text-sm text-panel-muted">Last updated: April 2026</p>
          </div>

          <Card className="space-y-8 p-6 md:p-8">
            {sections.map((section) => (
              <article key={section.title} className="space-y-4">
                <h2 className="text-2xl font-semibold text-panel-strong">{section.title}</h2>
                {section.body?.map((paragraph) => (
                  <p key={paragraph} className="text-sm leading-7 text-panel-copy">{paragraph}</p>
                ))}
                {section.cards ? (
                  <div className="grid gap-4 md:grid-cols-3">
                    {section.cards.map((card) => (
                      <Card key={card.title} className="p-5">
                        <h3 className="text-base font-semibold text-panel-strong">{card.title}</h3>
                        <p className="mt-2 text-sm leading-6 text-panel-copy">{card.copy}</p>
                      </Card>
                    ))}
                  </div>
                ) : null}
                {section.bullets ? (
                  <div className="space-y-3">
                    {section.bullets.map((bullet) => (
                      <div key={bullet.copy} className="flex items-center gap-3 rounded-2xl border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] px-4 py-3">
                        <bullet.icon className="size-5 shrink-0 text-brand" aria-hidden="true" />
                        <p className="text-sm leading-6 text-panel-copy">{bullet.copy}</p>
                      </div>
                    ))}
                  </div>
                ) : null}
                {section.note ? (
                <div className="flex items-center gap-3 rounded-2xl border border-[color-mix(in_srgb,var(--warning)_24%,white)] bg-[color-mix(in_srgb,var(--warning)_8%,white)] px-4 py-3 text-sm text-[color:var(--warning)] dark:border-[color-mix(in_srgb,var(--warning)_30%,transparent)] dark:bg-[color-mix(in_srgb,var(--warning)_14%,transparent)] dark:text-[color-mix(in_srgb,var(--warning)_86%,white)]">
                  <DatabaseZap className="size-5 shrink-0" aria-hidden="true" />
                  <p className="leading-6">{section.note}</p>
                </div>
                ) : null}
                {section.callout ? (
                  <div className="flex items-center gap-3 rounded-2xl border border-panel-table-wrap bg-[var(--dashboard-icon-button-surface)] px-4 py-3 text-sm text-panel-copy">
                    <Share2 className="size-5 shrink-0 text-brand" aria-hidden="true" />
                    <p className="leading-6">{section.callout}</p>
                  </div>
                ) : null}
              </article>
            ))}

            <article className="space-y-4">
              <h2 className="text-2xl font-semibold text-panel-strong">8. Contact Information</h2>
              <div className="grid gap-4 md:grid-cols-2">
                <Card className="p-5">
                  <span className="text-xs font-semibold uppercase tracking-[0.18em] text-panel-subtle">Administrator</span>
                  <p className="mt-2 text-sm text-panel-copy">Usalama Technology Limited</p>
                </Card>
                <Card className="p-5">
                  <span className="text-xs font-semibold uppercase tracking-[0.18em] text-panel-subtle">Support email</span>
                  <p className="mt-2 text-sm text-panel-copy">support@usalama.tech</p>
                </Card>
              </div>
            </article>
          </Card>

          <div className="flex flex-wrap items-center gap-3">
            <a href="/legal/chis-privacy-policy.pdf" download>
              <Button size="md">
                <Download className="size-4" aria-hidden="true" />
                Download Policy as PDF
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
