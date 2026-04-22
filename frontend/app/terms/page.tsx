 "use client";

import { ArrowLeft, CircleAlert, CircleHelp, Download, LayoutGrid, Siren, Sparkles } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";

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
  {
    title: "Risk predictions",
    icon: Sparkles,
  },
  {
    title: "Automated alerts",
    icon: Siren,
  },
  {
    title: "Decision support",
    icon: LayoutGrid,
  },
];

export default function TermsPage() {
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
            <span className="policy-chip">Terms</span>
            <span className="policy-current">Terms of Service</span>
          </div>
          <h1 className="policy-title">Terms of Service</h1>
          <p className="policy-updated">Last updated: April 2026</p>
        </section>

        <section className="policy-card">
          <article className="policy-section">
            <h2>1. Overview</h2>
            <p>
              The Climate Health Intelligence System (CHIS) is a climate-informed operational platform designed
              to support public health monitoring, preparedness, and response.
            </p>
            <div className="policy-highlight">
              By accessing or using this system, you acknowledge that you have read, understood, and agree to
              follow these terms.
            </div>
          </article>

          <article className="policy-section">
            <h2>2. Authorized Use</h2>
            <p>Access to CHIS is limited to approved users working in recognized operational roles.</p>
            <div className="policy-pill-grid">
              <span className="policy-pill">CHVs and healthcare workers</span>
              <span className="policy-pill">County health officials</span>
              <span className="policy-pill">Public health officers</span>
              <span className="policy-pill">Authorized partners</span>
            </div>
          </article>

          <article className="policy-section">
            <h2>3. User Responsibilities</h2>
            <div className="policy-stacked-cards">
              {responsibilityCards.map((card) => (
                <div key={card.title} className="policy-side-card">
                  <h3>{card.title}</h3>
                  <p>{card.copy}</p>
                </div>
              ))}
            </div>
          </article>

          <article className="policy-section">
            <h2>4. System Functionality</h2>
            <div className="policy-feature-grid">
              {functionalityCards.map((card) => {
                const Icon = card.icon;
                return (
                  <div key={card.title} className="policy-feature-card">
                    <Icon aria-hidden="true" />
                    <p>{card.title}</p>
                  </div>
                );
              })}
            </div>
          </article>

          <article className="policy-section">
            <h2>5. Important Disclaimer</h2>
            <div className="policy-note policy-note-alert">
              <CircleAlert aria-hidden="true" />
              <p>
                CHIS provides operational decision support informed by climate and risk signals. It does not
                replace professional judgment, official public health procedures, or verified field
                assessment.
              </p>
            </div>
          </article>

          <div className="policy-split-grid">
            <article className="policy-section policy-section-compact">
              <h2>6. System Availability</h2>
              <p>
                We work to keep the platform available and reliable, but uptime may be affected by
                maintenance, connectivity, or third-party service interruptions.
              </p>
            </article>

            <article className="policy-section policy-section-compact">
              <h2>7. Limitation of Liability</h2>
              <p>
                CHIS is provided to support public health operations. Users remain responsible for applying
                appropriate judgment and validating actions in real operational settings.
              </p>
            </article>
          </div>

          <article className="policy-section">
            <h2>8. Administration &amp; Updates</h2>
            <div className="policy-info-grid">
              <div className="policy-info-card">
                <h3>Account control</h3>
                <p>Access can be reviewed, limited, or removed when policy or operational requirements change.</p>
              </div>
              <div className="policy-info-card">
                <h3>Terms maintenance</h3>
                <p>These terms may be updated periodically. Material changes will be reflected on this page.</p>
              </div>
            </div>
          </article>

          <article className="policy-contact-banner">
            <div>
              <h2>Contact Information</h2>
              <p>For questions regarding these terms or system support.</p>
            </div>
            <div className="policy-contact-banner-meta">
              <p>Usalama Technology Limited</p>
              <p>support@usalama.tech</p>
            </div>
          </article>
        </section>

        <div className="policy-actions">
          <a href="/legal/chis-terms-of-service.pdf" download className="policy-download">
            <Download aria-hidden="true" />
            Download Terms as PDF
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
          <Link href="/privacy" className="login-footer-link">
            Privacy Policy
          </Link>
          <Link href="/terms" className="login-footer-link policy-footer-link-active">
            Terms of Service
          </Link>
        </div>
      </footer>
    </div>
  );
}
