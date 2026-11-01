"use client";

import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { TooltipContentProps } from "recharts";

import type { TrendingTopic } from "@/lib/trending";

const BAR_SIZE = 18;
const ROW_HEIGHT = 36;

function ChartTooltip({ active, payload }: Partial<TooltipContentProps<number, string>>) {
  const item = payload?.[0];
  if (!active || !item) return null;
  const topic = item.payload as TrendingTopic;
  return (
    <div className="rounded-md border bg-popover px-3 py-2 text-sm text-popover-foreground shadow-md">
      <p className="font-medium">{topic.category}</p>
      <p className="text-muted-foreground">
        <span className="font-medium text-foreground tabular-nums">{topic.signalCount}</span> signals
      </p>
    </div>
  );
}

/** Horizontal bars so long topic names stay readable at phone width. */
export function TrendingChart({ data }: { data: TrendingTopic[] }) {
  return (
    <div style={{ height: data.length * ROW_HEIGHT + 32 }} className="w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} layout="vertical" margin={{ top: 0, right: 16, bottom: 0, left: 0 }}>
          <CartesianGrid horizontal={false} stroke="var(--border)" />
          <XAxis
            type="number"
            allowDecimals={false}
            tickLine={false}
            axisLine={false}
            tick={{ fill: "var(--muted-foreground)", fontSize: 12 }}
          />
          <YAxis
            type="category"
            dataKey="category"
            width={112}
            tickLine={false}
            axisLine={false}
            tick={{ fill: "var(--foreground)", fontSize: 12 }}
          />
          <Tooltip cursor={{ fill: "var(--muted)" }} content={<ChartTooltip />} />
          <Bar
            dataKey="signalCount"
            name="Signals"
            fill="var(--primary)"
            barSize={BAR_SIZE}
            radius={[0, 4, 4, 0]}
            isAnimationActive={false}
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
