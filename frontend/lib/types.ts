export type SourceType = "rss" | "scrape" | "api" | "search" | "youtube";
export type Category = "ai_tech" | "business_finance" | "world_geopolitics" | "gulf_mena";
export type Importance = "low" | "medium" | "high";
export type Sentiment = "positive" | "neutral" | "negative";
export type RunStatus = "running" | "success" | "partial" | "failed";

export interface Entity { name: string; type: string; }

export interface NewsItem {
  id: string;
  org_id: string;
  user_id: string;
  source_id: string;
  source_type: SourceType;
  source_name: string;
  url: string;
  title: string;
  excerpt: string | null;
  published_at: string | null;
  collected_at: string;
  category: Category | null;
  summary_en: string | null;
  summary_ar: string | null;
  importance: Importance | null;
  importance_score: number | null;
  entities: Entity[];
  sentiment: Sentiment | null;
  language: string | null;
  status: string;
  digest_run_id: string | null;
}

export interface DigestRun {
  run_id: string;
  org_id: string;
  started_at: string;
  finished_at: string | null;
  status: RunStatus;
  collected: number;
  new: number;
  processed: number;
  high_importance: number;
  outputs: Record<string, string>;
  source_errors: { [k: string]: unknown }[];
  narrative: string | null;
}

export interface DashboardOut {
  latest_run: DigestRun | null;
  recent_runs: DigestRun[];
  category_counts: Record<string, number>;
  total_items: number;
}

export interface RunDetail { run: DigestRun; items: NewsItem[]; }

export interface SourceConfig {
  id: string;
  type: SourceType;
  name: string;
  url: string | null;
  query: string | null;
  category_hint: Category | null;
  selector: string | null;
  lang: string | null;
  country: string | null;
  channel_id: string | null;
  enabled: boolean;
}

export interface Watchlist { entities: string[]; keywords: string[]; }
