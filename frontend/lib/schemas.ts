import { z } from "zod";

// Zod schemas mirroring lib/types.ts. These validate API responses at the
// boundary (see lib/api.ts) so malformed backend payloads fail loudly instead
// of leaking bad data into the UI as blindly-cast `any`.

export const sourceTypeSchema = z.enum([
  "rss",
  "scrape",
  "api",
  "search",
  "youtube",
]);
export const categorySchema = z.enum([
  "ai_tech",
  "business_finance",
  "world_geopolitics",
  "gulf_mena",
]);
export const importanceSchema = z.enum(["low", "medium", "high"]);
export const sentimentSchema = z.enum(["positive", "neutral", "negative"]);
export const runStatusSchema = z.enum([
  "running",
  "success",
  "partial",
  "failed",
]);

export const entitySchema = z.object({
  name: z.string(),
  type: z.string(),
});

export const newsItemSchema = z.object({
  id: z.string(),
  org_id: z.string(),
  user_id: z.string(),
  source_id: z.string(),
  source_type: sourceTypeSchema,
  source_name: z.string(),
  url: z.string(),
  title: z.string(),
  excerpt: z.string().nullable(),
  published_at: z.string().nullable(),
  collected_at: z.string(),
  category: categorySchema.nullable(),
  summary_en: z.string().nullable(),
  summary_ar: z.string().nullable(),
  importance: importanceSchema.nullable(),
  importance_score: z.number().nullable(),
  entities: z.array(entitySchema),
  sentiment: sentimentSchema.nullable(),
  status: z.string(),
  digest_run_id: z.string().nullable(),
  image_url: z.string().nullish(),
});

export const digestRunSchema = z.object({
  run_id: z.string(),
  org_id: z.string(),
  started_at: z.string(),
  finished_at: z.string().nullable(),
  status: runStatusSchema,
  collected: z.number(),
  new: z.number(),
  processed: z.number(),
  high_importance: z.number(),
  outputs: z.record(z.string(), z.string()),
  source_errors: z.array(z.record(z.string(), z.unknown())),
  narrative: z.string().nullable(),
});

export const dashboardOutSchema = z.object({
  latest_run: digestRunSchema.nullable(),
  recent_runs: z.array(digestRunSchema),
  category_counts: z.record(z.string(), z.number()),
  total_items: z.number(),
});

export const runDetailSchema = z.object({
  run: digestRunSchema,
  items: z.array(newsItemSchema),
});

export const sourceConfigSchema = z.object({
  id: z.string(),
  type: sourceTypeSchema,
  name: z.string(),
  url: z.string().nullable(),
  query: z.string().nullable(),
  category_hint: categorySchema.nullable(),
  selector: z.string().nullable(),
  lang: z.string().nullable(),
  country: z.string().nullable(),
  channel_id: z.string().nullable(),
  enabled: z.boolean(),
});

export const watchlistSchema = z.object({
  entities: z.array(z.string()),
  keywords: z.array(z.string()),
});

// Collection-response schemas consumed by the SWR hooks.
export const digestRunListSchema = z.array(digestRunSchema);
export const newsItemListSchema = z.array(newsItemSchema);
export const sourceConfigListSchema = z.array(sourceConfigSchema);
