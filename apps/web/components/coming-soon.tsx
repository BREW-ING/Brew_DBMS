import { Construction } from "lucide-react";

import { EmptyState } from "@/components/empty-state";

/** Placeholder for routes that exist in the layout but are not built yet. */
export function ComingSoon({ title }: { title: string }) {
  return (
    <main className="mx-auto w-full max-w-5xl px-4 py-6 sm:py-10">
      <EmptyState icon={Construction} title={title} description="This page is not built yet." />
    </main>
  );
}
