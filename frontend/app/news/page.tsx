"use client";

import { useState } from "react";
import { Newspaper } from "lucide-react";
import { useNews } from "@/lib/hooks";
import type { Category, Importance } from "@/lib/types";
import { CATEGORY_LABELS, IMPORTANCE_LABELS } from "@/lib/labels";
import { PageHeader } from "@/components/layout/page-header";
import { EmptyState } from "@/components/common/empty-state";
import { AsyncBoundary } from "@/components/common/async-boundary";
import { NewsGroups } from "@/components/digests/news-groups";
import { Skeleton } from "@/components/ui/skeleton";
import { Card, CardContent } from "@/components/ui/card";
import { Label } from "@/components/ui/label";

const LIMIT_OPTIONS = [25, 50, 100] as const;
type Limit = (typeof LIMIT_OPTIONS)[number];

// NewsCard-shaped skeleton for loading state — mirrors the briefing layout
// (side thumbnail + top badges, headline, clamped takeaway, meta row).
function NewsCardSkeleton() {
  return (
    <div className="flex gap-3 rounded-xl bg-card ring-1 ring-foreground/10 border-l-2 border-foreground/10 px-4 py-3">
      <Skeleton className="hidden sm:block h-16 w-16 sm:h-20 sm:w-28 shrink-0 rounded-lg" />
      <div className="flex min-w-0 flex-1 flex-col gap-2">
        <div className="flex items-center gap-2">
          <Skeleton className="h-5 w-14 rounded-full" />
          <Skeleton className="h-5 w-24 rounded-full" />
        </div>
        <Skeleton className="h-4 w-3/4" />
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-5/6" />
        <div className="flex items-center gap-2">
          <Skeleton className="h-3 w-20" />
          <Skeleton className="h-3 w-14 font-mono" />
        </div>
      </div>
    </div>
  );
}

const selectClass =
  "h-8 rounded-lg border border-input bg-transparent px-2.5 py-1 text-sm outline-none transition-colors focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:bg-input/30";

export default function NewsPage() {
  const [category, setCategory] = useState<Category | undefined>(undefined);
  const [importance, setImportance] = useState<Importance | undefined>(
    undefined
  );
  const [limit, setLimit] = useState<Limit>(50);

  const { data, error, isLoading, mutate } = useNews({
    category,
    importance,
    limit,
  });

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="News"
        subtitle="Browse collected items"
        actions={
          data && (
            <span className="font-mono text-xs text-muted-foreground tabular-nums">
              {data.length} item{data.length !== 1 ? "s" : ""}
            </span>
          )
        }
      />

      {/* Filter bar */}
      <Card>
        <CardContent className="py-3">
          <div className="flex flex-wrap items-end gap-4">
            {/* Category filter */}
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="news-category">Category</Label>
              <select
                id="news-category"
                value={category ?? ""}
                onChange={(e) => {
                  const val = e.target.value;
                  setCategory(val ? (val as Category) : undefined);
                }}
                className={selectClass}
              >
                <option value="">All categories</option>
                {(Object.entries(CATEGORY_LABELS) as [Category, string][]).map(
                  ([val, label]) => (
                    <option key={val} value={val}>
                      {label}
                    </option>
                  )
                )}
              </select>
            </div>

            {/* Importance filter */}
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="news-importance">Importance</Label>
              <select
                id="news-importance"
                value={importance ?? ""}
                onChange={(e) => {
                  const val = e.target.value;
                  setImportance(val ? (val as Importance) : undefined);
                }}
                className={selectClass}
              >
                <option value="">All importance</option>
                {(
                  Object.entries(IMPORTANCE_LABELS) as [Importance, string][]
                ).map(([val, label]) => (
                  <option key={val} value={val}>
                    {label}
                  </option>
                ))}
              </select>
            </div>

            {/* Limit filter */}
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="news-limit">Limit</Label>
              <select
                id="news-limit"
                value={limit}
                onChange={(e) => setLimit(Number(e.target.value) as Limit)}
                className={selectClass}
              >
                {LIMIT_OPTIONS.map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </CardContent>
      </Card>

      <AsyncBoundary
        isLoading={isLoading && !data}
        error={error && !data ? error : undefined}
        isEmpty={!!data && data.length === 0}
        onRetry={() => mutate()}
        errorTitle="Couldn't load news"
        errorDescription="Is the API running on :8000?"
        skeleton={
          <div className="flex flex-col gap-3">
            {Array.from({ length: 5 }).map((_, i) => (
              <NewsCardSkeleton key={i} />
            ))}
          </div>
        }
        empty={
          <Card>
            <CardContent className="py-0">
              <EmptyState
                icon={Newspaper}
                title="No items match"
                description="Try clearing filters or running a digest."
              />
            </CardContent>
          </Card>
        }
      >
        {data && data.length > 0 && <NewsGroups items={data} />}
      </AsyncBoundary>
    </div>
  );
}
