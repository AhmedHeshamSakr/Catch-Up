"use client";

import Link from "next/link";
import { SearchX, AlertTriangle } from "lucide-react";
import { useRun } from "@/lib/hooks";
import { PageHeader } from "@/components/layout/page-header";
import { StatusBadge } from "@/components/common/status-badge";
import { EmptyState } from "@/components/common/empty-state";
import { ErrorState } from "@/components/common/error-state";
import { Skeleton } from "@/components/ui/skeleton";
import { Card, CardContent } from "@/components/ui/card";
import { NewsGroups } from "@/components/digests/news-groups";
import { OutputLinks } from "@/components/digests/output-links";
import { formatDateTime } from "@/lib/format";
import { ApiError } from "@/lib/api";

function truncateMiddle(str: string, maxLen = 40): string {
  if (str.length <= maxLen) return str;
  const half = Math.floor((maxLen - 3) / 2);
  return str.slice(0, half) + "..." + str.slice(str.length - half);
}

function RunDetailSkeleton() {
  return (
    <div className="flex flex-col gap-6">
      <Skeleton className="h-16 rounded-xl" />
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-16 rounded-xl" />
        ))}
      </div>
      <div className="flex flex-col gap-3">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-28 rounded-xl" />
        ))}
      </div>
    </div>
  );
}

/** Digest run detail, addressed by ``/digests?run=<id>`` (static-export friendly). */
export function RunDetail({ runId }: { runId: string }) {
  const { data, error, isLoading } = useRun(runId ?? null);

  const is404 =
    (error instanceof ApiError && error.status === 404) ||
    (!isLoading && !error && data && !data.run);

  if (isLoading && !data) {
    return (
      <div className="flex flex-col gap-6">
        <PageHeader title="Digest run" subtitle="Loading..." />
        <RunDetailSkeleton />
      </div>
    );
  }

  if (error && !is404) {
    return (
      <div className="flex flex-col gap-6">
        <PageHeader title="Digest run" />
        <Card>
          <CardContent className="py-0">
            <ErrorState
              title="Couldn't load run"
              description={error instanceof Error ? error.message : "An unexpected error occurred."}
            />
          </CardContent>
        </Card>
      </div>
    );
  }

  if (is404 || !data) {
    return (
      <div className="flex flex-col gap-6">
        <PageHeader title="Digest run" />
        <Card>
          <CardContent className="py-0">
            <EmptyState
              icon={SearchX}
              title="Run not found"
              description="This digest run does not exist."
              action={
                <Link
                  href="/digests"
                  className="text-sm text-link underline underline-offset-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-md"
                >
                  Back to digests
                </Link>
              }
            />
          </CardContent>
        </Card>
      </div>
    );
  }

  const { run, items } = data;

  return (
    <div className="flex flex-col gap-6">
      {/* Header */}
      <div className="flex flex-col gap-2">
        <PageHeader
          title="Digest run"
          subtitle={truncateMiddle(run.run_id)}
          actions={<OutputLinks outputs={run.outputs} />}
        />
        <div>
          <StatusBadge status={run.status} />
        </div>
      </div>

      {/* Meta strip */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div className="rounded-xl bg-card ring-1 ring-foreground/10 px-4 py-3">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground mb-1">
            Started
          </p>
          <p className="font-mono tabular-nums text-xs text-foreground leading-snug">
            {formatDateTime(run.started_at)}
          </p>
        </div>
        <div className="rounded-xl bg-card ring-1 ring-foreground/10 px-4 py-3">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground mb-1">
            Finished
          </p>
          <p className="font-mono tabular-nums text-xs text-foreground leading-snug">
            {run.finished_at ? formatDateTime(run.finished_at) : "—"}
          </p>
        </div>
        <div className="rounded-xl bg-card ring-1 ring-foreground/10 px-4 py-3">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground mb-1">
            Items
          </p>
          <p className="font-mono tabular-nums text-xs text-foreground">
            {run.collected} collected · {run.new} new · {run.processed} processed
          </p>
        </div>
        <div className="rounded-xl bg-card ring-1 ring-foreground/10 px-4 py-3">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground mb-1">
            High importance
          </p>
          <p className="font-mono tabular-nums text-xs text-foreground">
            {run.high_importance}
          </p>
        </div>
      </div>

      {/* Source errors */}
      {run.source_errors.length > 0 && (
        <div className="rounded-xl border border-amber-200 bg-amber-50 dark:border-amber-800/40 dark:bg-amber-950/20 px-4 py-3 flex flex-col gap-2">
          <div className="flex items-center gap-2">
            <AlertTriangle className="size-4 text-amber-600 dark:text-amber-400 shrink-0" aria-hidden="true" />
            <p className="text-sm font-medium text-amber-800 dark:text-amber-300">
              Source errors ({run.source_errors.length})
            </p>
          </div>
          <div className="flex flex-col gap-1.5">
            {run.source_errors.map((err, i) => (
              <div key={i} className="flex flex-col gap-0.5">
                <p className="text-xs font-medium text-amber-900 dark:text-amber-300">
                  {String((err as Record<string, unknown>).source_id ?? "unknown")}
                </p>
                <p className="text-xs text-amber-800 dark:text-amber-400 font-mono">
                  {String(
                    (err as Record<string, unknown>).error ??
                      JSON.stringify(err)
                  )}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Narrative */}
      {run.narrative && (
        <div className="rounded-xl border-l-2 border-emerald bg-card ring-1 ring-foreground/10 px-5 py-4">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-emerald mb-2">
            What matters most
          </p>
          <p className="text-sm text-foreground leading-relaxed">
            {run.narrative}
          </p>
        </div>
      )}

      {/* Items by importance */}
      {items.length === 0 ? (
        <p className="text-sm text-muted-foreground">No items in this run.</p>
      ) : (
        <NewsGroups items={items} />
      )}
    </div>
  );
}
