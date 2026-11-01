import "server-only";

import bcrypt from "bcryptjs";
import NextAuth, { type DefaultSession } from "next-auth";
import Credentials from "next-auth/providers/credentials";
import { z } from "zod";

import { getPool } from "@/lib/db";

// Mirrors CHECK (role IN ('user', 'curator')) on users.role.
export type Role = "user" | "curator";

declare module "next-auth" {
  interface User {
    role?: Role;
  }
  interface Session {
    user: { id: string; role: Role } & DefaultSession["user"];
  }
}

// next-auth/jwt only re-exports this module, so the augmentation has to target it.
declare module "@auth/core/jwt" {
  interface JWT {
    id?: string;
    role?: Role;
  }
}

export const BCRYPT_COST = 12;

// Compared against when the email is unknown, so a miss takes as long as a wrong password.
const DUMMY_HASH = "$2b$12$n5.xTe530T22SUfsrUTdSuP58ppMHKqKhwBKjA.jvJ29LfPCoxCxq";

const credentialsSchema = z.object({
  email: z.string().trim().toLowerCase().pipe(z.email()),
  password: z.string().min(1),
});

type UserRow = { id: string; email: string; name: string; password_hash: string; role: Role };

export const { handlers, auth, signIn, signOut } = NextAuth({
  session: { strategy: "jwt" },
  pages: { signIn: "/login" },
  providers: [
    Credentials({
      credentials: { email: {}, password: {} },
      async authorize(raw) {
        const parsed = credentialsSchema.safeParse(raw);
        if (!parsed.success) return null;
        const { email, password } = parsed.data;

        const { rows } = await getPool().query<UserRow>(
          "SELECT id, email, name, password_hash, role FROM users WHERE email = $1",
          [email],
        );
        const user = rows[0];
        const ok = await bcrypt.compare(password, user?.password_hash ?? DUMMY_HASH);
        if (!user || !ok) return null;

        // Only these fields reach the token; password_hash never leaves this function.
        return { id: user.id, email: user.email, name: user.name, role: user.role };
      },
    }),
  ],
  callbacks: {
    jwt({ token, user }) {
      if (user) {
        token.id = user.id;
        token.role = user.role;
      }
      return token;
    },
    session({ session, token }) {
      if (token.id) session.user.id = token.id;
      session.user.role = token.role ?? "user";
      return session;
    },
  },
});
