import Link from "next/link";

export function DashboardFooter() {
  return (
    <footer className="flex items-center justify-between gap-4 border-t border-[var(--dashboard-footer-line)] px-6 py-4 text-[0.76rem] text-[var(--dashboard-footer-ink)] opacity-90 max-[960px]:flex-col max-[960px]:items-start max-[640px]:px-4">
      <p>&copy; 2026 Climate Health Intelligence System. All rights reserved.</p>
      <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
        <Link href="/privacy" className="font-medium text-[var(--dashboard-footer-ink)] transition hover:text-[var(--login-link-hover)]">
          Privacy Policy
        </Link>
        <Link href="/terms" className="font-medium text-[var(--dashboard-footer-ink)] transition hover:text-[var(--login-link-hover)]">
          Terms of Service
        </Link>
      </div>
    </footer>
  );
}
