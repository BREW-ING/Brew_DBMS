"use server";

import bcrypt from "bcryptjs";
import { AuthError } from "next-auth";
import { z } from "zod";

import { BCRYPT_COST, signIn, signOut } from "@/lib/auth";
import { getPool } from "@/lib/db";

export type AuthFormState = { error?: string; fieldErrors?: Record<string, string> };

// Only same-site paths, so ?callbackUrl= can't bounce users to another domain.
function safeCallbackUrl(value: FormDataEntryValue | null): string {
  if (typeof value !== "string" || !value.startsWith("/") || value.startsWith("//") || value.startsWith("/\\")) {
    return "/";
  }
  return value;
}

function firstFieldErrors(error: z.ZodError): Record<string, string> {
  const out: Record<string, string> = {};
  for (const issue of error.issues) {
    const key = String(issue.path[0] ?? "form");
    out[key] ??= issue.message;
  }
  return out;
}

// signIn() redirects by throwing; only AuthErrors mean the sign-in itself failed.
async function signInOrError(email: string, password: string, redirectTo: string): Promise<AuthFormState> {
  try {
    await signIn("credentials", { email, password, redirectTo });
    return {};
  } catch (err) {
    if (err instanceof AuthError) {
      if (err.type === "CredentialsSignin") return { error: "Incorrect email or password." };
      console.error("auth: sign-in failed", err.type);
      return { error: "Couldn't sign you in right now. Try again in a moment." };
    }
    throw err;
  }
}

const loginSchema = z.object({
  email: z.string().trim().toLowerCase().pipe(z.email("Enter a valid email")),
  password: z.string().min(1, "Enter your password"),
});

export async function login(_prev: AuthFormState, formData: FormData): Promise<AuthFormState> {
  const parsed = loginSchema.safeParse({ email: formData.get("email"), password: formData.get("password") });
  if (!parsed.success) return { fieldErrors: firstFieldErrors(parsed.error) };

  return signInOrError(parsed.data.email, parsed.data.password, safeCallbackUrl(formData.get("callbackUrl")));
}

const registerSchema = z.object({
  name: z.string().trim().min(1, "Enter your name").max(80, "Keep it under 80 characters"),
  email: z.string().trim().toLowerCase().pipe(z.email("Enter a valid email")),
  // bcrypt ignores everything past 72 bytes.
  password: z
    .string()
    .min(8, "Use at least 8 characters")
    .refine((p) => Buffer.byteLength(p, "utf8") <= 72, "Keep it under 72 characters"),
});

export async function register(_prev: AuthFormState, formData: FormData): Promise<AuthFormState> {
  const parsed = registerSchema.safeParse({
    name: formData.get("name"),
    email: formData.get("email"),
    password: formData.get("password"),
  });
  if (!parsed.success) return { fieldErrors: firstFieldErrors(parsed.error) };
  const { name, email, password } = parsed.data;

  const passwordHash = await bcrypt.hash(password, BCRYPT_COST);
  try {
    const { rowCount } = await getPool().query(
      `INSERT INTO users (email, name, password_hash, role)
       VALUES ($1, $2, $3, 'user')
       ON CONFLICT (email) DO NOTHING`,
      [email, name, passwordHash],
    );
    if (rowCount === 0) return { fieldErrors: { email: "An account with this email already exists" } };
  } catch (err) {
    console.error("auth: register insert failed", err instanceof Error ? err.message : "unknown error");
    return { error: "Couldn't create your account right now. Try again in a moment." };
  }

  return signInOrError(email, password, "/");
}

export async function logout(): Promise<void> {
  await signOut({ redirectTo: "/login" });
}
