 "use client";

import { ArrowLeft, CircleAlert, CircleHelp, Download, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";

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
      "To generate and distribute climate-health risk insights to authorized users.",
      "To coordinate monitoring, alerts, and operational decision support.",
      "To secure the platform and limit access to authorized public health stakeholders.",
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
    <div className="policy-screen">
      <header className="forgot-topbar">
        <div className="policy-topbar-brand">
          <button
            type="button"
            className="policy-history-back"
            onClick={() => router.back()}
            aria-label="Go back"
          >
            <ArrowLeft aria-hidden="true" />
          </button>
          <Link href="/login" className="forgot-brand">
            CHIS
          </Link>
        </div>
        <div className="forgot-topbar-actions">
          <Link href="/login" className="forgot-topbar-link">
            Back to Login
          </Link>
          <span className="forgot-help-badge" aria-hidden="true">
            <CircleHelp />
          </span>
        </div>
      </header>

      <main className="policy-shell">
        <section className="policy-header">
          <div className="policy-header-row">
            <span className="policy-chip">Official Policy</span>
            <span className="policy-current">Privacy Policy</span>
          </div>
          <h1 className="policy-title">Privacy Policy</h1>
          <p className="policy-updated">Last updated: April 2026</p>
        </section>

        <section className="policy-card">
          {sections.map((section) => (
            <article key={section.title} className="policy-section">
              <h2>{section.title}</h2>

              {section.body?.map((paragraph) => (
                <p key={paragraph}>{paragraph}</p>
              ))}

              {section.cards ? (
                <div className="policy-info-grid">
                  {section.cards.map((card) => (
                    <div key={card.title} className="policy-info-card">
                      <h3>{card.title}</h3>
                      <p>{card.copy}</p>
                    </div>
                  ))}
                </div>
              ) : null}

              {section.bullets ? (
                <div className="policy-bullets">
                  {section.bullets.map((bullet) => (
                    <div key={bullet} className="policy-bullet">
                      <ShieldCheck aria-hidden="true" />
                      <p>{bullet}</p>
                    </div>
                  ))}
                </div>
              ) : null}

              {section.note ? (
                <div className="policy-note policy-note-alert">
                  <CircleAlert aria-hidden="true" />
                  <p>{section.note}</p>
                </div>
              ) : null}

              {section.callout ? (
                <div className="policy-note">
                  <ShieldCheck aria-hidden="true" />
                  <p>{section.callout}</p>
                </div>
              ) : null}
            </article>
          ))}

          <article className="policy-section">
            <h2>8. Contact Information</h2>
            <div className="policy-contact-grid">
              <div>
                <span className="policy-contact-label">Administrator</span>
                <p>Usalama Technology Limited</p>
              </div>
              <div>
                <span className="policy-contact-label">Support email</span>
                <p>support@usalama.tech</p>
              </div>
            </div>
          </article>
        </section>

        <div className="policy-actions">
          <a href="/legal/chis-privacy-policy.pdf" download className="policy-download">
            <Download aria-hidden="true" />
            Download Policy as PDF
          </a>
          <button type="button" className="policy-back-link" onClick={() => router.back()}>
            <ArrowLeft aria-hidden="true" />
            Back
          </button>
        </div>
      </main>

      <footer className="login-footer">
        <p>&copy; 2026 Climate Health Intelligence System. All rights reserved.</p>
        <div className="login-footer-links">
          <Link href="/privacy" className="login-footer-link policy-footer-link-active">
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
