import { ShieldBan } from "lucide-react";
import Link from "next/link";

export default function UnauthorizedPage() {
  return (
    <div className="auth-shell">
      <div className="auth-card stack">
        <p className="eyebrow">Access Restricted</p>
        <div className="title-row">
          <ShieldBan className="hero-icon" aria-hidden="true" />
          <h1 className="title">This dashboard role is not enabled here</h1>
        </div>
        <p className="subtitle">
          The current web dashboard is intended for Admin, Supervisor, and Analyst roles. CHV workflows
          remain field-focused and should not be forced into the dashboard shell.
        </p>
        <div className="status status-warning">
          Backend permissions remain the source of truth, and this screen simply reflects the current
          frontend scope.
        </div>
        <Link className="button" href="/login">
          Return to login
        </Link>
      </div>
    </div>
  );
}
