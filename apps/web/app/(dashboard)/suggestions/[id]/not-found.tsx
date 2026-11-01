import Link from "next/link";
import { SearchX } from "lucide-react";

import { EmptyState } from "@/components/empty-state";
import { Button } from "@/components/ui/button";

export default function SuggestionNotFound() {
  return (
    <EmptyState
      icon={SearchX}
      title="Suggestion not found"
      description="It may have expired after its source signal went stale."
    >
      <Button asChild variant="outline" size="sm">
        <Link href="/">Back to suggestions</Link>
      </Button>
    </EmptyState>
  );
}
