import type { Category, SourceType, Importance } from "./types";

export const CATEGORY_LABELS: Record<Category, string> = {
  ai_tech: "AI & Technology",
  business_finance: "Business & Finance",
  world_geopolitics: "World & Geopolitics",
  gulf_mena: "Gulf & MENA",
};
export const SOURCE_TYPE_LABELS: Record<SourceType, string> = {
  rss: "RSS", scrape: "Web Scrape", api: "News API", search: "Search Grounding", youtube: "YouTube",
};
export const IMPORTANCE_LABELS: Record<Importance, string> = {
  high: "High", medium: "Medium", low: "Low",
};
