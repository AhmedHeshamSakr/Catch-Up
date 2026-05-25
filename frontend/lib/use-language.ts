"use client";

import { useCallback, useSyncExternalStore } from "react";

// Display-language preference for article summaries. Persisted in localStorage
// and synced across tabs (storage event) and across components in the same tab
// (a custom in-tab event). Implemented with useSyncExternalStore so reads are
// SSR-safe (server snapshot is always the default) and never trip the lint rule
// `react-hooks/set-state-in-effect` — there is no useState/useEffect here.

export type Lang = "en" | "ar";

const STORAGE_KEY = "catchup.lang";
const EVENT_NAME = "catchup:lang";
const DEFAULT_LANG: Lang = "en";

function isLang(value: unknown): value is Lang {
  return value === "en" || value === "ar";
}

function read(): Lang {
  if (typeof window === "undefined") return DEFAULT_LANG;
  const stored = window.localStorage.getItem(STORAGE_KEY);
  return isLang(stored) ? stored : DEFAULT_LANG;
}

function subscribe(onChange: () => void): () => void {
  if (typeof window === "undefined") return () => {};
  window.addEventListener("storage", onChange);
  window.addEventListener(EVENT_NAME, onChange);
  return () => {
    window.removeEventListener("storage", onChange);
    window.removeEventListener(EVENT_NAME, onChange);
  };
}

function getSnapshot(): Lang {
  return read();
}

function getServerSnapshot(): Lang {
  return DEFAULT_LANG;
}

function writeLang(lang: Lang): void {
  if (typeof window === "undefined") return;
  const next: Lang = isLang(lang) ? lang : DEFAULT_LANG;
  window.localStorage.setItem(STORAGE_KEY, next);
  // Notify same-tab subscribers; the native `storage` event only fires in
  // *other* tabs, so we dispatch a custom event for this one.
  window.dispatchEvent(new Event(EVENT_NAME));
}

export interface UseLanguage {
  lang: Lang;
  setLang: (l: Lang) => void;
  toggle: () => void;
}

export function useLanguage(): UseLanguage {
  const lang = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);

  const setLang = useCallback((l: Lang) => {
    writeLang(l);
  }, []);

  const toggle = useCallback(() => {
    writeLang(read() === "en" ? "ar" : "en");
  }, []);

  return { lang, setLang, toggle };
}
