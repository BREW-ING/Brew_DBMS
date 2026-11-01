import type { Metadata } from "next";
import { Database } from "lucide-react";

import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { SourcesTable } from "@/components/sources-table";
import { listSources } from "@/lib/sources";

export const metadata: Metadata = { title: "Ingestion sources" };

export default async function SourcesPage() {
  const sources = await listSources();

  return (
    <>
      <PageHeader
        title="Ingestion sources"
        description="What fetch_signals pulls on its next run. Inactive sources are skipped; config keys override the adapter's defaults."
      />
      {sources.length > 0 ? (
        <SourcesTable sources={sources} />
      ) : (
        <EmptyState
          icon={Database}
          title="No ingestion sources"
          description="With no rows here, fetch_signals runs every adapter with its default config."
        />
      )}
    </>
  );
}
