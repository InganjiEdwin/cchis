import Link from "next/link";

export function DashboardFooter() {
  return (
    <footer className="dashboard-footer">
      <p>&copy; 2026 Climate Health Intelligence System. All rights reserved.</p>
      <div className="dashboard-footer-links">
        <Link href="/privacy" className="dashboard-footer-link">
          Privacy Policy
        </Link>
        <Link href="/terms" className="dashboard-footer-link">
          Terms of Service
        </Link>
      </div>
    </footer>
  );
}
