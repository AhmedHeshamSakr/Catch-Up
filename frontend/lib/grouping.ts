import type { Importance, NewsItem } from "./types";

// Importance-based grouping shared by the News list and the Digest detail page.
// Items with no importance are treated as LOW so nothing is dropped.

export type ImportanceBucket = "high" | "medium" | "low";

export const BUCKET_ORDER: ImportanceBucket[] = ["high", "medium", "low"];

// Section presentation per bucket — a scannable label that signals priority.
export const BUCKET_LABELS: Record<ImportanceBucket, string> = {
  high: "Top stories",
  medium: "Notable",
  low: "More",
};

export interface NewsGroup {
  bucket: ImportanceBucket;
  label: string;
  items: NewsItem[];
}

function bucketFor(importance: Importance | null | undefined): ImportanceBucket {
  if (importance === "high") return "high";
  if (importance === "medium") return "medium";
  return "low";
}

// Sort by importance_score descending, nulls/undefined last. Stable for equal
// scores (Array.prototype.sort is stable in modern engines).
function byScoreDesc(a: NewsItem, b: NewsItem): number {
  const sa = a.importance_score;
  const sb = b.importance_score;
  const av = sa === null || sa === undefined ? -Infinity : sa;
  const bv = sb === null || sb === undefined ? -Infinity : sb;
  return bv - av;
}

// Group items into HIGH / MEDIUM / LOW buckets, each sorted by score desc.
// Returns groups in priority order; empty buckets are still included so callers
// can decide whether to render them.
export function groupByImportance(items: NewsItem[]): NewsGroup[] {
  const buckets: Record<ImportanceBucket, NewsItem[]> = {
    high: [],
    medium: [],
    low: [],
  };
  for (const item of items) {
    buckets[bucketFor(item.importance)].push(item);
  }
  return BUCKET_ORDER.map((bucket) => ({
    bucket,
    label: BUCKET_LABELS[bucket],
    items: buckets[bucket].slice().sort(byScoreDesc),
  }));
}
