import { redirect } from "next/navigation";

import { auth } from "@/lib/auth";

// proxy.ts already gates these routes; this re-checks next to the data.
export default async function CuratorLayout({ children }: { children: React.ReactNode }) {
  const session = await auth();
  if (!session) redirect("/login");
  if (session.user.role !== "curator") redirect("/");
  return <>{children}</>;
}
