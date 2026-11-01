import { CircleAlert } from "lucide-react";

import { ReportBarChart, type ChartRow } from "@/components/report-bar-chart";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { runReport, type ReportDef, type ReportTable } from "@/lib/reports";

function chartRows(table: ReportTable, chart: NonNullable<ReportDef["chart"]>): ChartRow[] | null {
  const categoryIdx = table.columns.indexOf(chart.category);
  const series = chart.series.map((s) => ({ column: s.column, idx: table.columns.indexOf(s.column) }));
  if (categoryIdx < 0 || series.some((s) => s.idx < 0)) return null;
  return table.rows.map((row) => {
    const out: ChartRow = { category: String(row[categoryIdx] ?? "") };
    for (const s of series) out[s.column] = Number(row[s.idx] ?? 0);
    return out;
  });
}

function ResultTable({ table }: { table: ReportTable }) {
  if (table.rows.length === 0) return <p className="text-sm text-muted-foreground">No rows.</p>;
  // Right-align columns where every value is a number.
  const numeric = table.columns.map((_, i) => table.rows.every((r) => r[i] === null || typeof r[i] === "number"));
  return (
    <div className="max-h-96 overflow-auto rounded-md border">
      <table className="w-full text-sm">
        <thead className="sticky top-0 bg-muted">
          <tr className="text-left text-xs text-muted-foreground">
            {table.columns.map((c, i) => (
              <th key={c} className={`px-3 py-2 font-medium whitespace-nowrap ${numeric[i] ? "text-right" : ""}`}>
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {table.rows.map((row, r) => (
            <tr key={r} className="border-t">
              {row.map((cell, i) => (
                <td key={i} className={`px-3 py-1.5 ${numeric[i] ? "text-right tabular-nums" : ""}`}>
                  {cell ?? <span className="text-muted-foreground">—</span>}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export async function ReportCard({ def }: { def: ReportDef }) {
  const result = await runReport(def);
  const rows = result.status === "ok" && def.chart ? chartRows(result.table, def.chart) : null;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">{result.title}</CardTitle>
        <CardDescription className="text-xs text-muted-foreground">{def.note}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {result.status === "error" ? (
          <p className="flex items-start gap-2 rounded-md border border-dashed px-3 py-3 text-sm text-muted-foreground">
            <CircleAlert className="mt-0.5 size-4 shrink-0" aria-hidden />
            {result.message}
          </p>
        ) : (
          <>
            {def.chart && rows && rows.length > 0 ? <ReportBarChart data={rows} series={def.chart.series} /> : null}
            <ResultTable table={result.table} />
          </>
        )}
      </CardContent>
    </Card>
  );
}

export function ReportCardSkeleton() {
  return (
    <Card aria-hidden>
      <CardHeader>
        <Skeleton className="h-4 w-64 max-w-full" />
        <Skeleton className="h-3 w-80 max-w-full" />
      </CardHeader>
      <CardContent>
        <Skeleton className="h-32 w-full" />
      </CardContent>
    </Card>
  );
}
