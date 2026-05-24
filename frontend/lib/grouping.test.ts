import { describe, it, expect } from "vitest";
import { groupByImportance, BUCKET_ORDER } from "@/lib/grouping";
import type { NewsItem, Importance } from "@/lib/types";

function makeItem(
  id: string,
  importance: Importance | null,
  score: number | null
): NewsItem {
  return {
    id,
    org_id: "o",
    user_id: "u",
    source_id: "s",
    source_type: "rss",
    source_name: "Source",
    url: "https://example.com",
    title: `Item ${id}`,
    excerpt: null,
    published_at: null,
    collected_at: "2026-05-01T00:00:00Z",
    category: null,
    summary_en: null,
    summary_ar: null,
    importance,
    importance_score: score,
    entities: [],
    sentiment: null,
    language: null,
    status: "ok",
    digest_run_id: null,
  };
}

describe("groupByImportance", () => {
  it("buckets items into high/medium/low in priority order", () => {
    const groups = groupByImportance([
      makeItem("a", "low", 0.1),
      makeItem("b", "high", 0.9),
      makeItem("c", "medium", 0.5),
    ]);
    expect(groups.map((g) => g.bucket)).toEqual(BUCKET_ORDER);
    const byBucket = Object.fromEntries(groups.map((g) => [g.bucket, g.items]));
    expect(byBucket.high.map((i) => i.id)).toEqual(["b"]);
    expect(byBucket.medium.map((i) => i.id)).toEqual(["c"]);
    expect(byBucket.low.map((i) => i.id)).toEqual(["a"]);
  });

  it("treats null importance as low", () => {
    const groups = groupByImportance([makeItem("x", null, 0.2)]);
    const low = groups.find((g) => g.bucket === "low");
    expect(low?.items.map((i) => i.id)).toEqual(["x"]);
  });

  it("sorts within a bucket by importance_score descending", () => {
    const groups = groupByImportance([
      makeItem("low-score", "high", 0.2),
      makeItem("high-score", "high", 0.95),
      makeItem("mid-score", "high", 0.6),
    ]);
    const high = groups.find((g) => g.bucket === "high");
    expect(high?.items.map((i) => i.id)).toEqual([
      "high-score",
      "mid-score",
      "low-score",
    ]);
  });

  it("places null scores last within a bucket", () => {
    const groups = groupByImportance([
      makeItem("no-score", "medium", null),
      makeItem("scored", "medium", 0.4),
    ]);
    const medium = groups.find((g) => g.bucket === "medium");
    expect(medium?.items.map((i) => i.id)).toEqual(["scored", "no-score"]);
  });

  it("exposes a human label per group", () => {
    const groups = groupByImportance([
      makeItem("a", "high", 0.9),
      makeItem("b", "medium", 0.5),
      makeItem("c", "low", 0.1),
    ]);
    const labels = Object.fromEntries(groups.map((g) => [g.bucket, g.label]));
    expect(labels.high).toBe("Top stories");
    expect(labels.medium).toBe("Notable");
    expect(labels.low).toBe("More");
  });
});
