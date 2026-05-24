import { describe, it, expect } from "vitest";
import { fieldsForType, validateSource } from "@/lib/sources";

describe("fieldsForType", () => {
  it("scrape needs url + selector", () => {
    expect(fieldsForType("scrape")).toEqual(["url", "selector"]);
  });
  it("rss needs only url", () => {
    expect(fieldsForType("rss")).toEqual(["url"]);
  });
  it("api needs query/lang/country", () => {
    expect(fieldsForType("api")).toEqual(["query", "lang", "country"]);
  });
  it("search needs only query", () => {
    expect(fieldsForType("search")).toEqual(["query"]);
  });
  it("youtube needs only channel_id", () => {
    expect(fieldsForType("youtube")).toEqual(["channel_id"]);
  });
});

describe("validateSource", () => {
  it("flags missing selector for scrape", () => {
    const errs = validateSource({
      id: "s",
      name: "S",
      type: "scrape",
      url: "https://x",
      query: null,
      selector: null,
    });
    expect(errs.some((e) => /selector/i.test(e))).toBe(true);
  });

  it("passes a valid rss source", () => {
    const errs = validateSource({
      id: "s",
      name: "S",
      type: "rss",
      url: "https://x",
      query: null,
      selector: null,
    });
    expect(errs).toEqual([]);
  });

  it("flags empty id", () => {
    const errs = validateSource({
      id: "",
      name: "S",
      type: "rss",
      url: "https://x",
      query: null,
      selector: null,
    });
    expect(errs.some((e) => /id/i.test(e))).toBe(true);
  });

  it("flags missing url for rss", () => {
    const errs = validateSource({
      id: "s",
      name: "S",
      type: "rss",
      url: null,
      query: null,
      selector: null,
    });
    expect(errs.some((e) => /url/i.test(e))).toBe(true);
  });

  it("flags missing url for scrape", () => {
    const errs = validateSource({
      id: "s",
      name: "S",
      type: "scrape",
      url: null,
      query: null,
      selector: ".article",
    });
    expect(errs.some((e) => /url/i.test(e))).toBe(true);
  });

  it("flags missing query for api type", () => {
    const errs = validateSource({
      id: "s",
      name: "S",
      type: "api",
      url: null,
      query: null,
      selector: null,
    });
    expect(errs.some((e) => /query/i.test(e))).toBe(true);
  });

  it("flags missing query for search type", () => {
    const errs = validateSource({
      id: "s",
      name: "S",
      type: "search",
      url: null,
      query: null,
      selector: null,
    });
    expect(errs.some((e) => /query/i.test(e))).toBe(true);
  });

  it("flags empty name", () => {
    const errs = validateSource({
      id: "s",
      name: "",
      type: "rss",
      url: "https://x",
      query: null,
      selector: null,
    });
    expect(errs.some((e) => /name/i.test(e))).toBe(true);
  });

  it("passes valid scrape source", () => {
    const errs = validateSource({
      id: "my-scraper",
      name: "My Scraper",
      type: "scrape",
      url: "https://example.com",
      query: null,
      selector: ".article",
    });
    expect(errs).toEqual([]);
  });

  it("passes valid api source", () => {
    const errs = validateSource({
      id: "news-api",
      name: "News API",
      type: "api",
      url: null,
      query: "AI technology",
      selector: null,
    });
    expect(errs).toEqual([]);
  });

  it("passes valid search source", () => {
    const errs = validateSource({
      id: "g-search",
      name: "Google Search",
      type: "search",
      url: null,
      query: "latest AI news",
      selector: null,
    });
    expect(errs).toEqual([]);
  });

  it("flags whitespace-only id", () => {
    const errs = validateSource({
      id: "   ",
      name: "S",
      type: "rss",
      url: "https://x",
      query: null,
      selector: null,
    });
    expect(errs.some((e) => /id/i.test(e))).toBe(true);
  });

  it("flags missing channel_id for youtube source", () => {
    const errs = validateSource({
      id: "yt",
      name: "My Channel",
      type: "youtube",
      url: null,
      query: null,
      selector: null,
      channel_id: null,
    });
    expect(errs.some((e) => /channel id/i.test(e))).toBe(true);
  });

  it("passes a valid youtube source with channel_id", () => {
    const errs = validateSource({
      id: "yt",
      name: "My Channel",
      type: "youtube",
      url: null,
      query: null,
      selector: null,
      channel_id: "UCxxxxxxxxxxxxxxxxxxxxxx",
    });
    expect(errs).toEqual([]);
  });
});
