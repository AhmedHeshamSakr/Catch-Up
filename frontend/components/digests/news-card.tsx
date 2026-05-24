import { TrendingUp, Minus, TrendingDown } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { NewsItem, Sentiment } from "@/lib/types";
import { ImportanceBadge } from "@/components/common/importance-badge";
import { formatRelative, scorePct } from "@/lib/format";
import { cn } from "@/lib/utils";

interface NewsCardProps {
  item: NewsItem;
}

// Each sentiment pairs a color with a distinct icon shape so the signal is
// readable without relying on color alone (WCAG 1.4.1).
const sentimentMeta: Record<Sentiment, { color: string; icon: LucideIcon }> = {
  positive: { color: "text-emerald-600 dark:text-emerald-400", icon: TrendingUp },
  neutral: { color: "text-muted-foreground", icon: Minus },
  negative: { color: "text-red-600 dark:text-red-400", icon: TrendingDown },
};

export function NewsCard({ item }: NewsCardProps) {
  const timeLabel = item.published_at ?? item.collected_at;
  const displayText = item.summary_en ?? item.excerpt ?? null;
  const visibleEntities = (item.entities ?? []).slice(0, 6);

  return (
    <div className="flex flex-col gap-2 rounded-xl bg-card ring-1 ring-foreground/10 px-4 py-3">
      {/* Title row */}
      <div className="flex items-start justify-between gap-3">
        <a
          href={item.url}
          target="_blank"
          rel="noopener noreferrer"
          className="font-semibold text-link underline underline-offset-4 decoration-link/40 leading-snug transition-colors hover:decoration-link focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-md"
        >
          {item.title}
        </a>
        {item.sentiment &&
          (() => {
            const { color, icon: SentimentIcon } = sentimentMeta[item.sentiment];
            return (
              <SentimentIcon
                className={cn("mt-0.5 size-4 shrink-0", color)}
                aria-label={`Sentiment: ${item.sentiment}`}
              />
            );
          })()}
      </div>

      {/* Meta row */}
      <div className="flex flex-wrap items-center gap-2">
        <ImportanceBadge importance={item.importance} />
        <span className="text-xs text-muted-foreground">{item.source_name}</span>
        <span className="text-xs text-muted-foreground font-mono tabular-nums">
          {formatRelative(timeLabel)}
        </span>
        {item.importance_score !== null && item.importance_score !== undefined && (
          <span className="ml-auto text-xs text-muted-foreground font-mono tabular-nums">
            {scorePct(item.importance_score)}
          </span>
        )}
      </div>

      {/* Summary / excerpt */}
      {displayText && (
        <p className="text-sm text-muted-foreground leading-relaxed">
          {displayText}
        </p>
      )}

      {/* Arabic summary */}
      {item.summary_ar && (
        <p
          dir="rtl"
          lang="ar"
          className="text-sm text-muted-foreground leading-relaxed text-right"
        >
          {item.summary_ar}
        </p>
      )}

      {/* Entities */}
      {visibleEntities.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {visibleEntities.map((entity) => (
            <span
              key={`${entity.name}-${entity.type}`}
              className="inline-flex items-center rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground"
            >
              {entity.name}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
