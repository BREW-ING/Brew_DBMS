"use client";

import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { TooltipContentProps } from "recharts";

import type { ChartSeries } from "@/lib/reports";

export type ChartRow = { category: string } & Record<string, number | string>;

const BAR_SIZE = 12;

function ChartTooltip({ active, payload, series }: Partial<TooltipContentProps<number, string>> & { series: ChartSeries[] }) {
  const row = payload?.[0]?.payload as ChartRow | undefined;
  if (!active || !row) return null;
  return (
    <div className="rounded-md border bg-popover px-3 py-2 text-sm text-popover-foreground shadow-md">
      <p className="font-medium">{row.category}</p>
      {series.map((s) => (
        <p key={s.column} className="flex items-center gap-2 text-muted-foreground">
          <span className="size-2.5 rounded-sm" style={{ background: s.color }} aria-hidden />
          {s.name}: <span className="font-medium text-foreground tabular-nums">{row[s.column]}</span>
        </p>
      ))}
    </div>
  );
}

/** Horizontal bars, one row per category; grouped when there's more than one series. */
export function ReportBarChart({ data, series }: { data: ChartRow[]; series: ChartSeries[] }) {
  const rowHeight = series.length > 1 ? 40 : 30;
  return (
    <div className="space-y-2">
      {series.length > 1 ? (
        <ul className="flex flex-wrap gap-x-4 gap-y-1 px-3 text-xs text-muted-foreground sm:px-0">
          {series.map((s) => (
            <li key={s.column} className="flex items-center gap-1.5">
              <span className="size-2.5 rounded-sm" style={{ background: s.color }} aria-hidden />
              {s.name}
            </li>
          ))}
        </ul>
      ) : null}
      <div style={{ height: data.length * rowHeight + 32 }} className="w-full">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} layout="vertical" barGap={2} margin={{ top: 0, right: 16, bottom: 0, left: 0 }}>
            <CartesianGrid horizontal={false} stroke="var(--border)" />
            <XAxis
              type="number"
              tickLine={false}
              axisLine={false}
              tick={{ fill: "var(--muted-foreground)", fontSize: 12 }}
            />
            <YAxis
              type="category"
              dataKey="category"
              width={120}
              tickLine={false}
              axisLine={false}
              tick={{ fill: "var(--foreground)", fontSize: 12 }}
            />
            <Tooltip cursor={{ fill: "var(--muted)" }} content={<ChartTooltip series={series} />} />
            {series.map((s) => (
              <Bar
                key={s.column}
                dataKey={s.column}
                name={s.name}
                fill={s.color}
                barSize={BAR_SIZE}
                radius={[0, 4, 4, 0]}
                isAnimationActive={false}
              />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
