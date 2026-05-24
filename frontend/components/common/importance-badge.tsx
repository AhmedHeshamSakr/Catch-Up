import type { Importance } from "@/lib/types";
import { IMPORTANCE_LABELS } from "@/lib/labels";
import { cn } from "@/lib/utils";

interface ImportanceBadgeProps {
  importance: Importance | null;
  className?: string;
}

const importanceStyles: Record<Importance, string> = {
  high: "bg-red-50 text-red-600 dark:bg-red-950/40 dark:text-red-400",
  medium: "bg-amber-50 text-amber-700 dark:bg-amber-950/40 dark:text-amber-400",
  low: "bg-cyan-50 text-cyan-700 dark:bg-cyan-950/40 dark:text-cyan-400",
};

export function ImportanceBadge({ importance, className }: ImportanceBadgeProps) {
  if (importance === null) return null;

  return (
    <span
      className={cn(
        "inline-flex h-5 items-center rounded-full px-2 py-0.5 text-xs font-medium",
        importanceStyles[importance],
        className
      )}
    >
      {IMPORTANCE_LABELS[importance]}
    </span>
  );
}
