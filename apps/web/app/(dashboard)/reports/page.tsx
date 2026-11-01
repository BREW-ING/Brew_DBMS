import type { Metadata } from "next";
import { Suspense } from "react";

import { PageHeader } from "@/components/page-header";
import { ReportCard, ReportCardSkeleton } from "@/components/report-card";
import { REPORTS, type ReportDef } from "@/lib/reports";

export const metadata: Metadata = { title: "Reports" };

const sections: { heading: string; description: string; source: ReportDef["source"] }[] = [
  { heading: "Postgres", description: "Queries from db/postgres/reports.sql, run read-only.", source: "postgres" },
  { heading: "Neo4j", description: "Queries from db/neo4j/queries/reports.cypher.", source: "neo4j" },
];

export default function ReportsPage() {
  return (
    <>
      <PageHeader title="Reports" description="Live results of the demo queries against the relational and graph databases." />

      <div className="space-y-10">
        {sections.map(({ heading, description, source }) => (
          <section key={source} aria-labelledby={`reports-${source}`} className="space-y-4">
            <div className="space-y-1">
              <h2 id={`reports-${source}`} className="text-lg font-semibold tracking-tight">
                {heading}
              </h2>
              <p className="text-sm text-muted-foreground">{description}</p>
            </div>
            {/* Each card streams in on its own, so a slow or failing query doesn't hold up the rest. */}
            {REPORTS.filter((r) => r.source === source).map((def) => (
              <Suspense key={def.id} fallback={<ReportCardSkeleton />}>
                <ReportCard def={def} />
              </Suspense>
            ))}
          </section>
        ))}
      </div>
    </>
  );
}
