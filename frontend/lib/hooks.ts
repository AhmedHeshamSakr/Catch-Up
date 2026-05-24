"use client";

import useSWR from "swr";
import { api } from "@/lib/api";
import type {
  DashboardOut,
  DigestRun,
  RunDetail,
  NewsItem,
  SourceConfig,
  Watchlist,
  Category,
  Importance,
} from "@/lib/types";

export function useDashboard() {
  return useSWR<DashboardOut>("dashboard", () => api.getDashboard(), {
    refreshInterval: 15000,
  });
}

export function useRuns(limit?: number) {
  return useSWR<DigestRun[]>(["runs", limit], () => api.listRuns(limit));
}

export function useRun(runId: string | null) {
  return useSWR<RunDetail>(
    runId ? ["run", runId] : null,
    () => api.getRun(runId!)
  );
}

export function useNews(
  filters: {
    category?: Category;
    importance?: Importance;
    limit?: number;
  } = {}
) {
  return useSWR<NewsItem[]>(
    ["news", filters.category, filters.importance, filters.limit],
    () => api.listNews(filters)
  );
}

export function useSources() {
  return useSWR<SourceConfig[]>("sources", () => api.getSources());
}

export function useWatchlist() {
  return useSWR<Watchlist>("watchlist", () => api.getWatchlist());
}
