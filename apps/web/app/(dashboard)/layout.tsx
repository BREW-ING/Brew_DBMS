import { redirect } from "next/navigation";

import { auth } from "@/lib/auth";

// proxy.ts already gates these routes; this re-checks next to the data.
export default async function DashboardLayout({ children }: { children: React.ReactNode }) {
  const session = await auth();
  if (!session) redirect("/login");
  return <main className="mx-auto w-full max-w-5xl px-4 py-6 sm:py-10">{children}</main>;
}
