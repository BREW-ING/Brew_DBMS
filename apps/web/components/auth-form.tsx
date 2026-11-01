"use client";

import { useActionState } from "react";
import Link from "next/link";

import type { AuthFormState } from "@/app/(auth)/actions";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

type Field = {
  name: string;
  label: string;
  type: "text" | "email" | "password";
  autoComplete: string;
  minLength?: number;
};

export function AuthForm({
  title,
  description,
  submitLabel,
  fields,
  action,
  hidden,
  footer,
}: {
  title: string;
  description: string;
  submitLabel: string;
  fields: Field[];
  action: (prev: AuthFormState, formData: FormData) => Promise<AuthFormState>;
  hidden?: Record<string, string>;
  footer: { text: string; href: string; linkLabel: string };
}) {
  const [state, formAction, pending] = useActionState(action, {});

  return (
    <main className="mx-auto flex w-full max-w-sm flex-col px-4 py-10 sm:py-16">
      <Card>
        <CardHeader>
          <CardTitle>{title}</CardTitle>
          <CardDescription>{description}</CardDescription>
        </CardHeader>
        <form action={formAction} noValidate>
          <CardContent className="space-y-4">
            {hidden
              ? Object.entries(hidden).map(([name, value]) => (
                  <input key={name} type="hidden" name={name} value={value} />
                ))
              : null}
            {fields.map((field) => {
              const error = state.fieldErrors?.[field.name];
              const errorId = `${field.name}-error`;
              return (
                <div key={field.name} className="space-y-2">
                  <Label htmlFor={field.name}>{field.label}</Label>
                  <Input
                    id={field.name}
                    name={field.name}
                    type={field.type}
                    autoComplete={field.autoComplete}
                    minLength={field.minLength}
                    required
                    aria-invalid={error ? true : undefined}
                    aria-describedby={error ? errorId : undefined}
                  />
                  {error ? (
                    <p id={errorId} className="text-xs text-destructive">
                      {error}
                    </p>
                  ) : null}
                </div>
              );
            })}
            <p aria-live="polite" className="text-sm text-destructive empty:hidden">
              {state.error}
            </p>
          </CardContent>
          <CardFooter className="mt-6 flex-col items-stretch gap-3">
            <Button type="submit" disabled={pending}>
              {pending ? "Please wait…" : submitLabel}
            </Button>
            <p className="text-center text-sm text-muted-foreground">
              {footer.text}{" "}
              <Link href={footer.href} className="text-foreground underline underline-offset-4">
                {footer.linkLabel}
              </Link>
            </p>
          </CardFooter>
        </form>
      </Card>
    </main>
  );
}
