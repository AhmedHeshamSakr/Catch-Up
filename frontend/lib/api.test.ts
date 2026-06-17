import { it, expect, vi, beforeEach } from "vitest";
import { api, ApiError } from "@/lib/api";

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
  await api.putSources([{ id: "s", type: "rss", name: "S", url: "https://x", query: null, category_hint: null, selector: null, lang: null, country: null, channel_id: null, enabled: true }]);
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

it("sends X-API-Key header when NEXT_PUBLIC_API_KEY is set", async () => {
  process.env.NEXT_PUBLIC_API_KEY = "secret123";
  const fetchMock = vi.fn().mockResolvedValue(new Response("[]", { status: 200 }));
  vi.stubGlobal("fetch", fetchMock);
  await api.getSources();
  const headers = (fetchMock.mock.calls[0][1] as RequestInit).headers as Headers;
  expect(headers.get("X-API-Key")).toBe("secret123");
  delete process.env.NEXT_PUBLIC_API_KEY;
});

it("omits X-API-Key header when NEXT_PUBLIC_API_KEY is unset", async () => {
  delete process.env.NEXT_PUBLIC_API_KEY;
  const fetchMock = vi.fn().mockResolvedValue(new Response("[]", { status: 200 }));
  vi.stubGlobal("fetch", fetchMock);
  await api.getSources();
  const headers = (fetchMock.mock.calls[0][1] as RequestInit).headers as Headers;
  expect(headers.get("X-API-Key")).toBeNull();
});

it("throws ApiError on non-2xx without leaking the raw body into the message", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(new Response("<html>stack trace</html>", { status: 500 }))
  );
  const err = await api.getDashboard().catch((e) => e);
  expect(err).toBeInstanceOf(ApiError);
  expect(err.status).toBe(500);
  expect(err.message).not.toContain("<html>");
  expect(err.detail).toContain("<html>");
});

it("throws ApiError when a schema-validated response is malformed", async () => {
  // total_items should be a number; backend returns a string → schema rejects.
  const bad = { latest_run: null, recent_runs: [], category_counts: {}, total_items: "lots" };
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(new Response(JSON.stringify(bad), { status: 200 }))
  );
  const err = await api.getDashboard().catch((e) => e);
  expect(err).toBeInstanceOf(ApiError);
  expect(err.status).toBe(0);
});

it("resolveSource POSTs /api/sources/resolve with type+url and returns parsed json", async () => {
  const payload = { channel_id: "UC_abc123", name: "Test Channel", url: null };
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(payload), { status: 200 }));
  vi.stubGlobal("fetch", fetchMock);
  const result = await api.resolveSource("youtube", "https://youtube.com/@testchannel");
  const [url, opts] = fetchMock.mock.calls[0];
  expect(url).toBe("http://test/api/sources/resolve");
  expect(opts.method).toBe("POST");
  const body = JSON.parse(opts.body);
  expect(body.type).toBe("youtube");
  expect(body.url).toBe("https://youtube.com/@testchannel");
  expect(result.channel_id).toBe("UC_abc123");
  expect(result.name).toBe("Test Channel");
});
