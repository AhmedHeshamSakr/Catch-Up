import Link from "next/link";
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { formatDateTime } from "@/lib/format";
import type { DigestRun } from "@/lib/types";
import { cn } from "@/lib/utils";

interface RunHealthCardProps {
  run: DigestRun;
}

function Row({ label, value, valueClassName }: { label: string; value: string; valueClassName?: string }) {
  return (
    <div className="flex items-center justify-between gap-4 py-1.5 border-b border-border last:border-0">
      <span className="text-xs text-muted-foreground shrink-0">{label}</span>
      <span className={cn("text-xs font-mono tabular-nums text-foreground text-right", valueClassName)}>
        {value}
      </span>
    </div>
  );
}

export function RunHealthCard({ run }: RunHealthCardProps) {
  const hasErrors = run.source_errors.length > 0;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Latest run</CardTitle>
      </CardHeader>
      <CardContent className="pb-0">
        <Row label="Started" value={formatDateTime(run.started_at)} />
        <Row
          label="Finished"
          value={run.finished_at ? formatDateTime(run.finished_at) : "—"}
        />
        <div className="flex items-center justify-between gap-4 py-1.5 border-b border-border">
          <span className="text-xs text-muted-foreground shrink-0">Pipeline</span>
          <span className="text-xs font-mono tabular-nums text-foreground">
            {run.collected}
            <span className="text-muted-foreground mx-1">→</span>
            {run.new}
            <span className="text-muted-foreground mx-1">→</span>
            {run.processed}
          </span>
        </div>
        <div className="flex items-center justify-between gap-4 py-1.5">
          <span className="text-xs text-muted-foreground shrink-0">Source errors</span>
          <span
            className={cn(
              "text-xs font-mono tabular-nums",
              hasErrors ? "text-red-600 dark:text-red-400" : "text-foreground"
            )}
          >
            {run.source_errors.length}
          </span>
        </div>
      </CardContent>
      <CardFooter>
        <Link
          href={`/digests?run=${run.run_id}`}
          className="text-xs text-link underline underline-offset-4 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-md"
        >
          View run detail →
        </Link>
      </CardFooter>
    </Card>
  );
}
