"use client";

import Link from "next/link";

import { useAuth } from "@/components/auth-provider";
import type { UserRole } from "@/lib/auth";
import { hasRole } from "@/lib/roles";

type RoleGateProps = {
  allowedRoles: UserRole[];
  title: string;
  message: string;
  children: React.ReactNode;
};

export function RoleGate({ allowedRoles, title, message, children }: RoleGateProps) {
  const { currentUser } = useAuth();

  if (!currentUser) {
    return null;
  }

  if (hasRole(currentUser.role, allowedRoles)) {
    return <>{children}</>;
  }

  return (
    <section className="page-grid">
      <article className="card">
        <h3>{title}</h3>
        <p className="muted">{message}</p>
        <div className="status status-warning" style={{ marginTop: "1rem" }}>
          This route exists, but your current role does not have access to it.
        </div>
        <div style={{ marginTop: "1rem" }}>
          <Link href="/overview" className="button">
            Return to Overview
          </Link>
        </div>
      </article>
    </section>
  );
}
