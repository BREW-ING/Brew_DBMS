import type { Metadata } from "next";

import { login } from "@/app/(auth)/actions";
import { AuthForm } from "@/components/auth-form";

export const metadata: Metadata = { title: "Sign in" };

export default async function LoginPage({ searchParams }: { searchParams: Promise<{ callbackUrl?: string }> }) {
  const { callbackUrl } = await searchParams;

  return (
    <AuthForm
      title="Sign in"
      description="Welcome back to Brew."
      submitLabel="Sign in"
      action={login}
      hidden={{ callbackUrl: callbackUrl ?? "/" }}
      fields={[
        { name: "email", label: "Email", type: "email", autoComplete: "email" },
        { name: "password", label: "Password", type: "password", autoComplete: "current-password" },
      ]}
      footer={{ text: "New here?", href: "/register", linkLabel: "Create an account" }}
    />
  );
}
