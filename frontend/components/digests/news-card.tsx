import type { NewsItem } from "@/lib/types";
import { ImportanceBadge } from "@/components/common/importance-badge";
import { formatRelative, scorePct } from "@/lib/format";
import { cn } from "@/lib/utils";

interface NewsCardProps {
  item: NewsItem;
}

const sentimentStyles = {
  positive: "bg-emerald-500 dark:bg-emerald-400",
  neutral: "bg-muted-foreground/40",
  negative: "bg-red-500 dark:bg-red-400",
} as const;

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
          className="font-semibold text-foreground leading-snug hover:text-cyan transition-colors"
        >
          {item.title}
        </a>
        {item.sentiment && (
          <span
            className={cn(
              "mt-1 size-2 shrink-0 rounded-full",
              sentimentStyles[item.sentiment]
            )}
            aria-label={`Sentiment: ${item.sentiment}`}
          />
        )}
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
          {visibleEntities.map((entity, i) => (
            <span
              key={i}
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
