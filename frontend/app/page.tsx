"use client";

import { Inbox, Activity, TrendingUp, Layers, AlertCircle } from "lucide-react";
import { useDashboard } from "@/lib/hooks";
import { PageHeader } from "@/components/layout/page-header";
import { RunNowButton } from "@/components/layout/run-now-button";
import { EmptyState } from "@/components/common/empty-state";
import { ErrorState } from "@/components/common/error-state";
import { StatusBadge } from "@/components/common/status-badge";
import { StatCard } from "@/components/dashboard/stat-card";
import { CategoryBreakdown } from "@/components/dashboard/category-breakdown";
import { RunHealthCard } from "@/components/dashboard/run-health-card";
import { Skeleton } from "@/components/ui/skeleton";
import { Card, CardContent } from "@/components/ui/card";

function DashboardSkeleton() {
  return (
    <div className="flex flex-col gap-6">
      {/* Stat row */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-24 rounded-xl" />
        ))}
      </div>
      {/* Narrative */}
      <Skeleton className="h-28 rounded-xl" />
      {/* Two-column */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <Skeleton className="h-48 rounded-xl" />
        <Skeleton className="h-48 rounded-xl" />
      </div>
    </div>
  );
}

export default function DashboardPage() {
  const { data, error, isLoading, mutate } = useDashboard();

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Dashboard"
        subtitle="Your news intelligence at a glance"
        actions={<RunNowButton onStarted={() => mutate()} />}
      />

      {isLoading && !data && <DashboardSkeleton />}

      {error && !data && (
        <Card>
          <CardContent className="py-0">
            <ErrorState
              title="Couldn't load dashboard"
              description="Is the API reachable?"
              onRetry={() => mutate()}
            />
          </CardContent>
        </Card>
      )}

      {data && data.total_items === 0 && !data.latest_run && (
        <Card>
          <CardContent className="py-0">
            <EmptyState
              icon={Inbox}
              title="No digests yet"
              description="Run your first digest to populate the dashboard."
              action={<RunNowButton onStarted={() => mutate()} />}
            />
          </CardContent>
        </Card>
      )}

      {data && (data.total_items > 0 || data.latest_run) && (
        <>
          {/* Stat row */}
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <StatCard
              label="Total items"
              value={data.total_items}
              icon={Layers}
            />
            <StatCard
              label="Latest run"
              value={
                data.latest_run ? (
                  <StatusBadge status={data.latest_run.status} />
                ) : (
                  <span className="text-muted-foreground">—</span>
                )
              }
              icon={Activity}
            />
            <StatCard
              label="New in latest"
              value={data.latest_run?.new ?? "—"}
              icon={TrendingUp}
            />
            <StatCard
              label="High importance"
              value={data.latest_run?.high_importance ?? "—"}
              icon={AlertCircle}
            />
          </div>

          {/* Narrative */}
          {data.latest_run && (
            <div className="rounded-xl border-l-2 border-emerald bg-card ring-1 ring-foreground/10 px-5 py-4">
              <p className="text-[10px] font-semibold uppercase tracking-wider text-emerald mb-2">
                What matters most
              </p>
              {data.latest_run.narrative ? (
                <p className="text-sm text-foreground leading-relaxed">
                  {data.latest_run.narrative}
                </p>
              ) : (
                <p className="text-sm text-muted-foreground">
                  No narrative for the latest run yet.
                </p>
              )}
            </div>
          )}

          {/* Two-column row */}
          {data.latest_run && (
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <CategoryBreakdown counts={data.category_counts} />
              <RunHealthCard run={data.latest_run} />
            </div>
          )}
        </>
      )}
    </div>
  );
}
