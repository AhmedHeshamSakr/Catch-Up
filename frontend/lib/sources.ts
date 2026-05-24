import type { SourceType } from "@/lib/types";

export type SourceField = "url" | "selector" | "query" | "lang" | "country" | "channel_id";

export function fieldsForType(type: SourceType): SourceField[] {
  switch (type) {
    case "rss":
      return ["url"];
    case "scrape":
      return ["url", "selector"];
    case "api":
      return ["query", "lang", "country"];
    case "search":
      return ["query"];
    case "youtube":
      return ["channel_id"];
  }
}

export const REQUIRED_BY_TYPE: Record<SourceType, SourceField[]> = {
  rss: ["url"],
  scrape: ["url", "selector"],
  api: ["query"],
  search: ["query"],
  youtube: ["channel_id"],
};

const FIELD_LABELS: Record<SourceField, string> = {
  url: "URL",
  selector: "CSS selector",
  query: "Query",
  lang: "Language",
  country: "Country",
  channel_id: "Channel ID",
};

const TYPE_LABELS: Record<SourceType, string> = {
  rss: "RSS",
  scrape: "Scrape",
  api: "API",
  search: "Search",
  youtube: "YouTube",
};

/** Returns array of human-readable validation errors. Empty array means valid. */
export function validateSource(s: {
  id: string;
  name: string;
  type: SourceType;
  url: string | null;
  query: string | null;
  selector: string | null;
  channel_id?: string | null;
}): string[] {
  const errors: string[] = [];

  if (!s.id || s.id.trim() === "") {
    errors.push("ID is required");
  }

  if (!s.name || s.name.trim() === "") {
    errors.push("Name is required");
  }

  const required = REQUIRED_BY_TYPE[s.type];
  for (const field of required) {
    const value = s[field as keyof typeof s];
    if (!value || (typeof value === "string" && value.trim() === "")) {
      errors.push(
        `${FIELD_LABELS[field]} is required for ${TYPE_LABELS[s.type]} sources`
      );
    }
  }

  return errors;
}
