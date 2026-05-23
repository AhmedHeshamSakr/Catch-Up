"use client";

import Link from "next/link";
import { FileText, ChevronRight } from "lucide-react";
import { useRuns } from "@/lib/hooks";
import { PageHeader } from "@/components/layout/page-header";
import { RunNowButton } from "@/components/layout/run-now-button";
import { StatusBadge } from "@/components/common/status-badge";
import { EmptyState } from "@/components/common/empty-state";
import { ErrorState } from "@/components/common/error-state";
import { Skeleton } from "@/components/ui/skeleton";
import { Card, CardContent } from "@/components/ui/card";
import {
  Table,
  TableHeader,
  TableBody,
  TableHead,
  TableRow,
  TableCell,
} from "@/components/ui/table";
import { formatDateTime } from "@/lib/format";

function DigestTableSkeleton() {
  return (
    <div className="flex flex-col gap-2">
      {Array.from({ length: 5 }).map((_, i) => (
        <Skeleton key={i} className="h-10 rounded-lg w-full" />
      ))}
    </div>
  );
}

export default function DigestsPage() {
  const { data: runs, error, isLoading, mutate } = useRuns();

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Digests"
        subtitle="Past digest runs"
        actions={<RunNowButton onStarted={() => mutate()} />}
      />

      {isLoading && !runs && <DigestTableSkeleton />}

      {error && !runs && (
        <Card>
          <CardContent className="py-0">
            <ErrorState
              title="Couldn't load digests"
              description="Is the API running on :8000?"
              onRetry={() => mutate()}
            />
          </CardContent>
        </Card>
      )}

      {runs && runs.length === 0 && (
        <Card>
          <CardContent className="py-0">
            <EmptyState
              icon={FileText}
              title="No digests yet"
              description="Run a digest to see it here."
              action={<RunNowButton onStarted={() => mutate()} />}
            />
          </CardContent>
        </Card>
      )}

      {runs && runs.length > 0 && (
        <Card>
          <CardContent className="px-0 py-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="pl-4">Started</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Collected</TableHead>
                  <TableHead>New</TableHead>
                  <TableHead>Processed</TableHead>
                  <TableHead>High</TableHead>
                  <TableHead>Outputs</TableHead>
                  <TableHead className="pr-4 w-8" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {runs.map((run) => (
                  <TableRow key={run.run_id} className="group cursor-pointer">
                    <TableCell className="pl-4">
                      <Link
                        href={`/digests/${run.run_id}`}
                        className="font-mono tabular-nums text-xs text-foreground hover:text-cyan transition-colors"
                      >
                        {formatDateTime(run.started_at)}
                      </Link>
                    </TableCell>
                    <TableCell>
                      <StatusBadge status={run.status} />
                    </TableCell>
                    <TableCell className="font-mono tabular-nums text-xs text-muted-foreground">
                      {run.collected}
                    </TableCell>
                    <TableCell className="font-mono tabular-nums text-xs text-muted-foreground">
                      {run.new}
                    </TableCell>
                    <TableCell className="font-mono tabular-nums text-xs text-muted-foreground">
                      {run.processed}
                    </TableCell>
                    <TableCell className="font-mono tabular-nums text-xs text-muted-foreground">
                      {run.high_importance}
                    </TableCell>
                    <TableCell className="font-mono tabular-nums text-xs text-muted-foreground">
                      {Object.keys(run.outputs).length}
                    </TableCell>
                    <TableCell className="pr-4">
                      <Link
                        href={`/digests/${run.run_id}`}
                        aria-label={`View run started ${formatDateTime(run.started_at)}`}
                        className="flex items-center justify-center text-muted-foreground/40 group-hover:text-muted-foreground transition-colors"
                      >
                        <ChevronRight className="size-4" />
                      </Link>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
