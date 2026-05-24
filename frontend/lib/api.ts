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

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const base = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";
  const res = await fetch(base + path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) throw new ApiError(res.status, await res.text());
  return (await res.json()) as T;
}

export const api = {
  getDashboard(): Promise<DashboardOut> {
    return request<DashboardOut>("/api/dashboard");
  },

  listRuns(limit?: number): Promise<DigestRun[]> {
    const path = limit !== undefined ? `/api/runs?limit=${limit}` : "/api/runs";
    return request<DigestRun[]>(path);
  },

  getRun(runId: string): Promise<RunDetail> {
    return request<RunDetail>(`/api/runs/${encodeURIComponent(runId)}`);
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
    return request<NewsItem[]>(path);
  },

  getSources(): Promise<SourceConfig[]> {
    return request<SourceConfig[]>("/api/sources");
  },

  putSources(list: SourceConfig[]): Promise<{ status: string; count: number }> {
    return request<{ status: string; count: number }>("/api/sources", {
      method: "PUT",
      body: JSON.stringify(list),
    });
  },

  getWatchlist(): Promise<Watchlist> {
    return request<Watchlist>("/api/watchlist");
  },

  putWatchlist(wl: Watchlist): Promise<{ status: string }> {
    return request<{ status: string }>("/api/watchlist", {
      method: "PUT",
      body: JSON.stringify(wl),
    });
  },

  triggerRun(): Promise<{ status: string }> {
    return request<{ status: string }>("/api/runs", {
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
