"use client";

import { useState } from "react";
import { TrendingUp, Minus, TrendingDown, ChevronDown } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { NewsItem, Sentiment } from "@/lib/types";
import { ImportanceBadge } from "@/components/common/importance-badge";
import { CATEGORY_LABELS } from "@/lib/labels";
import { categoryColor } from "@/lib/categories";
import { formatRelative, scorePct } from "@/lib/format";
import { useLanguage } from "@/lib/use-language";
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

// A summary in a single language plus the direction metadata needed to render
// Arabic correctly (RTL, right-aligned).
interface LangSummary {
  text: string;
  dir: "rtl" | "ltr";
  lang: string;
  align: string;
}

function isHttpUrl(value: string | null | undefined): value is string {
  return (
    typeof value === "string" &&
    (value.startsWith("http://") || value.startsWith("https://"))
  );
}

export function NewsCard({ item }: NewsCardProps) {
  const { lang } = useLanguage();
  const [expanded, setExpanded] = useState(false);
  const [imageError, setImageError] = useState(false);

  const timeLabel = item.published_at ?? item.collected_at;

  const en = item.summary_en?.trim() || null;
  const ar = item.summary_ar?.trim() || null;
  const excerpt = item.excerpt?.trim() || null;

  const arSummary: LangSummary | null = ar
    ? { text: ar, dir: "rtl", lang: "ar", align: "text-right" }
    : null;
  const enSummary: LangSummary | null = en
    ? { text: en, dir: "ltr", lang: "en", align: "text-left" }
    : null;

  // Preferred-language takeaway with graceful fallback: preferred → other
  // language → excerpt → nothing.
  const preferred = lang === "ar" ? arSummary : enSummary;
  const fallback = lang === "ar" ? enSummary : arSummary;
  const takeaway: LangSummary | null =
    preferred ??
    fallback ??
    (excerpt ? { text: excerpt, dir: "ltr", lang: "en", align: "text-left" } : null);

  // The OTHER-language summary shown only when expanded (skip if it's what we
  // already displayed as the takeaway).
  const otherSummary =
    takeaway === preferred ? fallback : takeaway === fallback ? preferred : null;

  const entities = item.entities ?? [];
  const hasScore =
    item.importance_score !== null && item.importance_score !== undefined;
  const showImage = isHttpUrl(item.image_url) && !imageError;
  const catColor = categoryColor(item.category);

  const sentiment = item.sentiment
    ? sentimentMeta[item.sentiment]
    : null;

  return (
    <article
      className={cn(
        "flex gap-3 rounded-xl bg-card ring-1 ring-foreground/10 px-4 py-3 border-l-2 transition-colors hover:ring-foreground/20",
        catColor.accent
      )}
    >
      {/* Thumbnail (graceful: only valid http(s) urls, hides on error).
          Intentionally a plain <img>, NOT next/image: thumbnails come from
          arbitrary news domains we can't enumerate in `images.remotePatterns`
          (next/image's default loader returns 400 for unlisted hosts), and we
          must not proxy third-party images through our own server. See the
          local Next.js Image doc (remotePatterns + Image Optimization API
          security notes). */}
      {showImage && (
        // eslint-disable-next-line @next/next/no-img-element -- see note above
        <img
          src={item.image_url as string}
          alt={item.title}
          loading="lazy"
          decoding="async"
          onError={() => setImageError(true)}
          className="hidden sm:block h-16 w-16 sm:h-20 sm:w-28 shrink-0 rounded-lg object-cover bg-muted"
        />
      )}

      <div className="flex min-w-0 flex-1 flex-col gap-2">
        {/* Top line: importance + category + sentiment */}
        <div className="flex items-center gap-2">
          <ImportanceBadge importance={item.importance} />
          {item.category && (
            <span
              className={cn(
                "inline-flex h-5 items-center rounded-full px-2 py-0.5 text-xs font-medium",
                catColor.chip
              )}
            >
              {CATEGORY_LABELS[item.category]}
            </span>
          )}
          {sentiment && (
            <sentiment.icon
              className={cn("ml-auto size-4 shrink-0", sentiment.color)}
              aria-label={`Sentiment: ${item.sentiment}`}
            />
          )}
        </div>

        {/* Headline */}
        <a
          href={item.url}
          target="_blank"
          rel="noopener noreferrer"
          className="font-semibold text-link underline underline-offset-4 decoration-link/40 leading-snug transition-colors hover:decoration-link focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-md"
        >
          {item.title}
        </a>

        {/* Takeaway — primary text color, clamped for even, scannable cards */}
        {takeaway && (
          <p
            dir={takeaway.dir}
            lang={takeaway.lang}
            className={cn(
              "text-sm text-foreground leading-relaxed",
              !expanded && "line-clamp-3",
              takeaway.dir === "rtl" && takeaway.align
            )}
          >
            {takeaway.text}
          </p>
        )}

        {/* Expanded details: other-language summary, all entities, score */}
        {expanded && (
          <div className="flex flex-col gap-2">
            {otherSummary && (
              <p
                dir={otherSummary.dir}
                lang={otherSummary.lang}
                className={cn(
                  "text-sm text-muted-foreground leading-relaxed",
                  otherSummary.dir === "rtl" && otherSummary.align
                )}
              >
                {otherSummary.text}
              </p>
            )}
            {entities.length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                {entities.map((entity) => (
                  <span
                    key={`${entity.name}-${entity.type}`}
                    className="inline-flex items-center rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground"
                  >
                    {entity.name}
                  </span>
                ))}
              </div>
            )}
            {hasScore && (
              <p className="text-xs text-muted-foreground">
                Importance score:{" "}
                <span className="font-mono tabular-nums">
                  {scorePct(item.importance_score)}
                </span>
              </p>
            )}
          </div>
        )}

        {/* Meta + expand control */}
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <span className="truncate">{item.source_name}</span>
          <span aria-hidden="true">·</span>
          <span className="font-mono tabular-nums shrink-0">
            {formatRelative(timeLabel)}
          </span>
          {hasScore && (
            <span className="font-mono tabular-nums shrink-0 ml-auto">
              {scorePct(item.importance_score)}
            </span>
          )}
          {(otherSummary || entities.length > 0 || hasScore || takeaway) && (
            <button
              type="button"
              onClick={() => setExpanded((v) => !v)}
              aria-expanded={expanded}
              className={cn(
                "inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 font-medium text-foreground/80 transition-colors hover:text-foreground hover:bg-foreground/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                !hasScore && "ml-auto"
              )}
            >
              {expanded ? "Less" : "Details"}
              <ChevronDown
                className={cn(
                  "size-3.5 transition-transform",
                  expanded && "rotate-180"
                )}
                aria-hidden="true"
              />
            </button>
          )}
        </div>
      </div>
    </article>
  );
}
