import { it, expect, vi, beforeEach } from "vitest";
import { api } from "@/lib/api";

beforeEach(() => { vi.restoreAllMocks(); process.env.NEXT_PUBLIC_API_BASE = "http://test"; });

it("getDashboard hits /api/dashboard and returns parsed json", async () => {
  const payload = { latest_run: null, recent_runs: [], category_counts: {}, total_items: 0 };
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(payload), { status: 200 }));
  vi.stubGlobal("fetch", fetchMock);
  const out = await api.getDashboard();
  expect(fetchMock).toHaveBeenCalledWith("http://test/api/dashboard", expect.any(Object));
  expect(out.total_items).toBe(0);
});

it("listNews builds query string from filters", async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response("[]", { status: 200 }));
  vi.stubGlobal("fetch", fetchMock);
  await api.listNews({ category: "ai_tech", importance: "high", limit: 25 });
  expect(fetchMock.mock.calls[0][0]).toBe("http://test/api/news?category=ai_tech&importance=high&limit=25");
});

it("listNews omits undefined filters", async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response("[]", { status: 200 }));
  vi.stubGlobal("fetch", fetchMock);
  await api.listNews({ limit: 50 });
  expect(fetchMock.mock.calls[0][0]).toBe("http://test/api/news?limit=50");
});

it("putSources sends PUT with JSON body", async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ status: "ok", count: 1 }), { status: 200 }));
  vi.stubGlobal("fetch", fetchMock);
  await api.putSources([{ id: "s", type: "rss", name: "S", url: "https://x", query: null, category_hint: null, selector: null, lang: null, country: null, enabled: true }]);
  const [, opts] = fetchMock.mock.calls[0];
  expect(opts.method).toBe("PUT");
  expect(JSON.parse(opts.body)[0].id).toBe("s");
});

it("triggerRun POSTs /api/runs", async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ status: "started" }), { status: 202 }));
  vi.stubGlobal("fetch", fetchMock);
  await api.triggerRun();
  const [url, opts] = fetchMock.mock.calls[0];
  expect(url).toBe("http://test/api/runs");
  expect(opts.method).toBe("POST");
});

it("throws ApiError on non-2xx", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("nope", { status: 500 })));
  await expect(api.getDashboard()).rejects.toThrow();
});
