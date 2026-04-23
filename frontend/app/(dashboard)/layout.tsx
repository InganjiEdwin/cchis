import { redirect } from "next/navigation";

import { ProtectedShell } from "@/components/protected-shell";
import { fetchServerSession } from "@/lib/server-session";
import { isDashboardRole } from "@/lib/roles";

export default async function DashboardLayout({ children }: { children: React.ReactNode }) {
  const session = await fetchServerSession();

  if (session) {
    if (!session.authenticated || !session.user) {
      redirect("/login");
    }

    if (!isDashboardRole(session.user.role)) {
      redirect("/unauthorized");
    }
  }

  return <ProtectedShell>{children}</ProtectedShell>;
}
