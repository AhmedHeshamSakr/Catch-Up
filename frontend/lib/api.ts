import type { ZodType } from "zod";
import type {
  DashboardOut,
  DigestRun,
  RunDetail,
  NewsItem,
  SourceConfig,
  SourceType,
  Watchlist,
  Category,
  Importance,
} from "@/lib/types";
import {
  dashboardOutSchema,
  digestRunListSchema,
  runDetailSchema,
  newsItemListSchema,
  sourceConfigListSchema,
  watchlistSchema,
} from "@/lib/schemas";

export class ApiError extends Error {
  /**
   * @param status HTTP status code (0 for client-side validation failures).
   * @param message Clean, UI-safe message — never a raw response body.
   * @param detail Optional raw body / validation detail kept for debugging only.
   */
  constructor(
    public status: number,
    message: string,
    public detail?: string
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(
  path: string,
  init?: RequestInit,
  schema?: ZodType<T>
): Promise<T> {
  const base = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";
  // Optional shared API key. Sent only when configured; exposed to the browser
  // (NEXT_PUBLIC_*), so use only for trusted/internal deploys — real per-user
  // auth is a separate milestone. Must match the backend's API_KEY.
  const apiKey = process.env.NEXT_PUBLIC_API_KEY;
  // Normalize to Headers so an explicit init.headers (plain object, tuple array,
  // OR a Headers instance) always wins and our defaults only fill the gaps.
  const headers = new Headers(init?.headers);
  if (!headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  if (apiKey && !headers.has("X-API-Key")) headers.set("X-API-Key", apiKey);
  const res = await fetch(base + path, { ...init, headers });
  if (!res.ok) {
    // Keep the raw body as debug detail but never surface it (could be HTML /
    // a stack trace) as the user-facing message.
    const detail = await res.text().catch(() => "");
    throw new ApiError(
      res.status,
      `Request failed with status ${res.status}`,
      detail || undefined
    );
  }

  const json = await res.json();

  if (schema) {
    const result = schema.safeParse(json);
    if (!result.success) {
      throw new ApiError(
        0,
        "Received an unexpected response from the server.",
        result.error.message
      );
    }
    return result.data;
  }

  return json as T;
}

export const api = {
  getDashboard(): Promise<DashboardOut> {
    return request<DashboardOut>("/api/dashboard", undefined, dashboardOutSchema);
  },

  listRuns(limit?: number): Promise<DigestRun[]> {
    const path = limit !== undefined ? `/api/runs?limit=${limit}` : "/api/runs";
    return request<DigestRun[]>(path, undefined, digestRunListSchema);
  },

  getRun(runId: string): Promise<RunDetail> {
    return request<RunDetail>(
      `/api/runs/${encodeURIComponent(runId)}`,
      undefined,
      runDetailSchema
    );
  },

  listNews(filters?: {
    category?: Category;
    importance?: Importance;
    limit?: number;
  }): Promise<NewsItem[]> {
    const qs = new URLSearchParams();
    if (filters?.category !== undefined) qs.append("category", filters.category);
    if (filters?.importance !== undefined) qs.append("importance", filters.importance);
    if (filters?.limit !== undefined) qs.append("limit", String(filters.limit));
    const qStr = qs.toString();
    const path = qStr ? `/api/news?${qStr}` : "/api/news";
    return request<NewsItem[]>(path, undefined, newsItemListSchema);
  },

  getSources(): Promise<SourceConfig[]> {
    return request<SourceConfig[]>("/api/sources", undefined, sourceConfigListSchema);
  },

  putSources(list: SourceConfig[]): Promise<{ status: string; count: number }> {
    return request<{ status: string; count: number }>("/api/sources", {
      method: "PUT",
      body: JSON.stringify(list),
    });
  },

  getWatchlist(): Promise<Watchlist> {
    return request<Watchlist>("/api/watchlist", undefined, watchlistSchema);
  },

  putWatchlist(wl: Watchlist): Promise<{ status: string }> {
    return request<{ status: string }>("/api/watchlist", {
      method: "PUT",
      body: JSON.stringify(wl),
    });
  },

  triggerRun(): Promise<{ status: string; run_id: string }> {
    return request<{ status: string; run_id: string }>("/api/runs", {
      method: "POST",
    });
  },

  resolveSource(
    type: SourceType,
    url: string
  ): Promise<{ channel_id?: string | null; url?: string | null; name?: string | null }> {
    return request("/api/sources/resolve", {
      method: "POST",
      body: JSON.stringify({ type, url }),
    });
  },
};
