import type { Metadata } from "next";
import { TrendingUp } from "lucide-react";

import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { TrendingChart } from "@/components/trending-chart";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getTrendingTopics } from "@/lib/mock-data";

export const metadata: Metadata = { title: "Trending" };

const TOP_N = 8;

export default async function TrendingPage() {
  const topics = (await getTrendingTopics()).slice(0, TOP_N);

  return (
    <>
      <PageHeader title="Trending" description="Problem areas with the most new signals in the last 14 days." />

      {topics.length > 0 ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Top topics by new signals</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 px-2 sm:px-5">
            <TrendingChart data={topics} />
            <details className="px-3 text-sm sm:px-0">
              <summary className="cursor-pointer text-muted-foreground hover:text-foreground">
                Show as table
              </summary>
              <table className="mt-3 w-full">
                <thead>
                  <tr className="border-b text-left text-xs text-muted-foreground">
                    <th className="py-2 font-medium">Topic</th>
                    <th className="py-2 text-right font-medium">Signals</th>
                  </tr>
                </thead>
                <tbody>
                  {topics.map((t) => (
                    <tr key={t.category} className="border-b last:border-0">
                      <td className="py-2">{t.category}</td>
                      <td className="py-2 text-right tabular-nums">{t.signalCount}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </details>
          </CardContent>
        </Card>
      ) : (
        <EmptyState
          icon={TrendingUp}
          title="Nothing trending yet"
          description="Trends appear once new problem signals have been ingested in the last two weeks."
        />
      )}
    </>
  );
}
