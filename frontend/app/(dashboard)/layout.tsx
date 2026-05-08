import { headers } from "next/headers";
import { redirect } from "next/navigation";

import { ProtectedShell } from "@/components/protected-shell";
import { requiresPolicyAcceptance } from "@/lib/auth";
import { hasPageCapability } from "@/lib/capabilities";
import { buildPolicyReviewRoute } from "@/lib/navigation";
import { fetchServerSession } from "@/lib/server-session";

export default async function DashboardLayout({ children }: { children: React.ReactNode }) {
  const session = await fetchServerSession({ allowRefreshBootstrap: false });

  if (!session?.authenticated || !session.user) {
    return <ProtectedShell>{children}</ProtectedShell>;
  }

  if (!hasPageCapability(session.user, "dashboard")) {
    redirect("/unauthorized");
  }

  if (requiresPolicyAcceptance(session.user)) {
    const headerList = await headers();
    redirect(buildPolicyReviewRoute(headerList.get("x-cchis-current-path")));
  }

  return <ProtectedShell>{children}</ProtectedShell>;
}
