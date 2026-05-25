import { renderHook, act } from "@testing-library/react";
import { describe, it, expect, beforeEach } from "vitest";
import { useLanguage } from "@/lib/use-language";

beforeEach(() => {
  window.localStorage.clear();
});

describe("useLanguage", () => {
  it("defaults to \"en\" when nothing is stored", () => {
    const { result } = renderHook(() => useLanguage());
    expect(result.current.lang).toBe("en");
  });

  it("returns a stored value", () => {
    window.localStorage.setItem("catchup.lang", "ar");
    const { result } = renderHook(() => useLanguage());
    expect(result.current.lang).toBe("ar");
  });

  it("falls back to \"en\" for an invalid stored value", () => {
    window.localStorage.setItem("catchup.lang", "fr");
    const { result } = renderHook(() => useLanguage());
    expect(result.current.lang).toBe("en");
  });

  it("setLang persists to localStorage and updates the snapshot", () => {
    const { result } = renderHook(() => useLanguage());
    act(() => result.current.setLang("ar"));
    expect(window.localStorage.getItem("catchup.lang")).toBe("ar");
    expect(result.current.lang).toBe("ar");
  });

  it("toggle flips en↔ar", () => {
    const { result } = renderHook(() => useLanguage());
    act(() => result.current.toggle());
    expect(result.current.lang).toBe("ar");
    act(() => result.current.toggle());
    expect(result.current.lang).toBe("en");
  });
});
