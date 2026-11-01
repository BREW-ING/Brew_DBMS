import { CircleDot, FileText, MessageSquare, type LucideIcon } from "lucide-react";

import type { SignalSource } from "@/lib/suggestions";
import { cn } from "@/lib/utils";

const sources: Record<SignalSource, { label: string; icon: LucideIcon }> = {
  github: { label: "GitHub", icon: CircleDot },
  arxiv: { label: "arXiv", icon: FileText },
  hn: { label: "Hacker News", icon: MessageSquare },
};

export function sourceLabel(source: SignalSource): string {
  return sources[source].label;
}

export function SourceBadge({ source, className }: { source: SignalSource; className?: string }) {
  const { label, icon: Icon } = sources[source];
  return (
    <span className={cn("inline-flex items-center gap-1.5 text-xs font-medium", className)}>
      <Icon className="size-3.5" aria-hidden />
      {label}
    </span>
  );
}
