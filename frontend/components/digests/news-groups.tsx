"use client";

import type { NewsItem } from "@/lib/types";
import { groupByImportance } from "@/lib/grouping";
import { NewsCard } from "@/components/digests/news-card";

interface NewsGroupsProps {
  items: NewsItem[];
}

function SectionHeader({ label, count }: { label: string; count: number }) {
  return (
    <h3 className="mb-3 flex items-baseline gap-2 text-sm font-semibold text-foreground">
      {label}
      <span className="font-mono tabular-nums text-xs font-normal text-muted-foreground">
        {count}
      </span>
    </h3>
  );
}

// Renders items bucketed by importance into Top stories / Notable / More.
// The low-priority "More" group is collapsed by default to keep noise down.
export function NewsGroups({ items }: NewsGroupsProps) {
  const groups = groupByImportance(items);

  return (
    <div className="flex flex-col gap-8">
      {groups.map((group) => {
        if (group.items.length === 0) return null;

        if (group.bucket === "low") {
          return (
            <details key={group.bucket} className="group">
              <summary className="mb-3 flex cursor-pointer list-none items-baseline gap-2 text-sm font-semibold text-foreground rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
                <span className="text-muted-foreground transition-transform group-open:rotate-90">
                  ▸
                </span>
                {group.label}
                <span className="font-mono tabular-nums text-xs font-normal text-muted-foreground">
                  {group.items.length}
                </span>
              </summary>
              <div className="flex flex-col gap-3">
                {group.items.map((item) => (
                  <NewsCard key={item.id} item={item} />
                ))}
              </div>
            </details>
          );
        }

        return (
          <section key={group.bucket}>
            <SectionHeader label={group.label} count={group.items.length} />
            <div className="flex flex-col gap-3">
              {group.items.map((item) => (
                <NewsCard key={item.id} item={item} />
              ))}
            </div>
          </section>
        );
      })}
    </div>
  );
}
