import type { Metadata } from "next";
import { Inter } from "next/font/google";

import { NavBar } from "@/components/nav-bar";
import { ThemeProvider } from "@/components/theme-provider";
import { auth } from "@/lib/auth";

import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });

export const metadata: Metadata = {
  title: { default: "Brew", template: "%s · Brew" },
  description: "Project ideas grounded in real problems, matched to your skills and team.",
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const session = await auth();
  // Pass only what the nav renders; nothing else from the session goes to the client.
  const user = session ? { name: session.user.name ?? session.user.email ?? "", role: session.user.role } : null;

  return (
    <html lang="en" className={inter.variable} suppressHydrationWarning>
      <body className="min-h-dvh font-sans">
        <ThemeProvider attribute="class" defaultTheme="system" enableSystem disableTransitionOnChange>
          <NavBar user={user} />
          {children}
        </ThemeProvider>
      </body>
    </html>
  );
}
