"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FileText, ChevronRight } from "lucide-react";
import { useRuns } from "@/lib/hooks";
import { PageHeader } from "@/components/layout/page-header";
import { RunNowButton } from "@/components/layout/run-now-button";
import { StatusBadge } from "@/components/common/status-badge";
import { EmptyState } from "@/components/common/empty-state";
import { AsyncBoundary } from "@/components/common/async-boundary";
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

/** List of past digest runs. Each row drills into ``/digests?run=<id>``. */
export function RunsList() {
  const router = useRouter();
  const { data: runs, error, isLoading, mutate } = useRuns();

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Digests"
        subtitle="Past digest runs"
        actions={<RunNowButton onStarted={() => mutate()} />}
      />

      <AsyncBoundary
        isLoading={isLoading && !runs}
        error={error && !runs ? error : undefined}
        isEmpty={!!runs && runs.length === 0}
        onRetry={() => mutate()}
        errorTitle="Couldn't load digests"
        errorDescription="Is the API running?"
        skeleton={<DigestTableSkeleton />}
        empty={
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
        }
      >
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
                    <TableRow
                      key={run.run_id}
                      role="link"
                      tabIndex={0}
                      onClick={() => router.push(`/digests?run=${encodeURIComponent(run.run_id)}`)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          router.push(`/digests?run=${encodeURIComponent(run.run_id)}`);
                        }
                      }}
                      className="group cursor-pointer hover:bg-muted/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    >
                      <TableCell className="pl-4 font-mono tabular-nums text-xs text-foreground group-hover:text-cyan transition-colors">
                        {formatDateTime(run.started_at)}
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
                          href={`/digests?run=${encodeURIComponent(run.run_id)}`}
                          aria-label={`View run started ${formatDateTime(run.started_at)}`}
                          onClick={(e) => e.stopPropagation()}
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
      </AsyncBoundary>
    </div>
  );
}
