import type { Metadata } from "next";

import { register } from "@/app/(auth)/actions";
import { AuthForm } from "@/components/auth-form";

export const metadata: Metadata = { title: "Create an account" };

export default function RegisterPage() {
  return (
    <AuthForm
      title="Create an account"
      description="Get project ideas matched to your skills and team."
      submitLabel="Create account"
      action={register}
      fields={[
        { name: "name", label: "Name", type: "text", autoComplete: "name" },
        { name: "email", label: "Email", type: "email", autoComplete: "email" },
        { name: "password", label: "Password", type: "password", autoComplete: "new-password", minLength: 8 },
      ]}
      footer={{ text: "Already have an account?", href: "/login", linkLabel: "Sign in" }}
    />
  );
}
