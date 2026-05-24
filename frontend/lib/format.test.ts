import { describe, it, expect } from "vitest";
import { formatDateTime, formatRelative, scorePct } from "@/lib/format";

describe("formatDateTime", () => {
  it("formats a UTC ISO string to '24 May 2026, 09:30 UTC'", () => {
    expect(formatDateTime("2026-05-24T09:30:00Z")).toBe("24 May 2026, 09:30 UTC");
  });

  it("zero-pads day and time parts", () => {
    expect(formatDateTime("2026-01-03T08:05:00Z")).toBe("03 Jan 2026, 08:05 UTC");
  });

  it("handles September without 'Sept' ambiguity", () => {
    expect(formatDateTime("2026-09-15T14:00:00Z")).toBe("15 Sep 2026, 14:00 UTC");
  });
});

describe("formatRelative", () => {
  const base = new Date("2026-05-24T10:00:00Z");

  it("returns 'just now' for <60s", () => {
    expect(formatRelative("2026-05-24T09:59:30Z", base)).toBe("just now");
  });

  it("returns 'Xm ago' for <60m", () => {
    expect(formatRelative("2026-05-24T09:15:00Z", base)).toBe("45m ago");
  });

  it("returns 'Xh ago' for <24h", () => {
    expect(formatRelative("2026-05-24T04:00:00Z", base)).toBe("6h ago");
  });

  it("returns 'Xd ago' for <7d", () => {
    expect(formatRelative("2026-05-21T10:00:00Z", base)).toBe("3d ago");
  });

  it("falls back to formatDateTime for >=7d", () => {
    expect(formatRelative("2026-05-10T09:30:00Z", base)).toBe("10 May 2026, 09:30 UTC");
  });
});

describe("scorePct", () => {
  it("converts 0.42 to '42%'", () => {
    expect(scorePct(0.42)).toBe("42%");
  });

  it("rounds to nearest int", () => {
    expect(scorePct(0.999)).toBe("100%");
    expect(scorePct(0.001)).toBe("0%");
  });

  it("returns '—' for null", () => {
    expect(scorePct(null)).toBe("—");
  });

  it("returns '—' for undefined", () => {
    expect(scorePct(undefined)).toBe("—");
  });
});
