"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ClipboardCheck, Coffee, Database, Lightbulb, LogOut, TrendingUp, User, Users } from "lucide-react";

import { logout } from "@/app/(auth)/actions";
import { ThemeToggle } from "@/components/theme-toggle";
import { Button } from "@/components/ui/button";
import type { Role } from "@/lib/auth";
import { cn } from "@/lib/utils";

const links = [
  { href: "/", label: "Suggestions", icon: Lightbulb },
  { href: "/trending", label: "Trending", icon: TrendingUp },
  { href: "/teammates", label: "Teammates", icon: Users },
  { href: "/profile", label: "Profile", icon: User },
] as const;

const curatorLinks = [
  { href: "/review", label: "Review", icon: ClipboardCheck },
  { href: "/sources", label: "Sources", icon: Database },
] as const;

function isActive(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/" || pathname.startsWith("/suggestions");
  return pathname.startsWith(href);
}

export function NavBar({ user }: { user: { name: string; role: Role } | null }) {
  const pathname = usePathname();
  const visibleLinks = user ? [...links, ...(user.role === "curator" ? curatorLinks : [])] : [];

  return (
    <header className="sticky top-0 z-40 border-b bg-background/85 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-5xl items-center gap-2 px-4 sm:gap-6">
        <Link href="/" className="flex items-center gap-2 font-semibold tracking-tight">
          <Coffee className="size-5 text-primary" aria-hidden />
          Brew
        </Link>
        <nav aria-label="Main" className="flex flex-1 items-center gap-1 overflow-x-auto">
          {visibleLinks.map(({ href, label, icon: Icon }) => {
            const active = isActive(pathname, href);
            return (
              <Link
                key={href}
                href={href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "flex items-center gap-1.5 rounded-md px-2 py-1.5 text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-foreground sm:px-2.5",
                  active && "bg-accent text-foreground",
                )}
              >
                <Icon className="size-4" aria-hidden />
                <span className="sr-only sm:not-sr-only">{label}</span>
              </Link>
            );
          })}
        </nav>
        <ThemeToggle />
        {user ? (
          <form action={logout}>
            <Button type="submit" variant="ghost" size="sm" aria-label={`Sign out ${user.name}`}>
              <LogOut aria-hidden />
              <span className="sr-only sm:not-sr-only">Sign out</span>
            </Button>
          </form>
        ) : null}
      </div>
    </header>
  );
}
