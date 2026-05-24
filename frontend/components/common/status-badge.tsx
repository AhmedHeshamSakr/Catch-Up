import type { RunStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

interface StatusBadgeProps {
  status: RunStatus;
  className?: string;
}

const statusStyles: Record<RunStatus, string> = {
  success: "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-400",
  partial: "bg-amber-50 text-amber-700 dark:bg-amber-950/40 dark:text-amber-400",
  failed: "bg-red-50 text-red-600 dark:bg-red-950/40 dark:text-red-400",
  running: "bg-cyan-50 text-cyan-700 dark:bg-cyan-950/40 dark:text-cyan-400",
};

const statusDotStyles: Record<RunStatus, string> = {
  success: "bg-emerald-500 dark:bg-emerald-400",
  partial: "bg-amber-500 dark:bg-amber-400",
  failed: "bg-red-500 dark:bg-red-400",
  running: "bg-cyan-500 dark:bg-cyan-400 animate-pulse",
};

const statusLabels: Record<RunStatus, string> = {
  success: "Success",
  partial: "Partial",
  failed: "Failed",
  running: "Running",
};

export function StatusBadge({ status, className }: StatusBadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex h-5 items-center gap-1.5 rounded-full px-2 py-0.5 font-sans text-xs font-medium",
        statusStyles[status],
        className
      )}
    >
      <span
        className={cn("size-1.5 rounded-full shrink-0", statusDotStyles[status])}
        aria-hidden="true"
      />
      {statusLabels[status]}
    </span>
  );
}
