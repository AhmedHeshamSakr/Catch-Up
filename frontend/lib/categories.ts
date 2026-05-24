import type { Category } from "./types";

// Per-category color treatments for the category chip and an optional thin card
// accent. Each palette is chosen to read AA in both light and dark modes,
// mirroring the validated ImportanceBadge approach (light: -50 bg / -700 text,
// dark: -950/40 bg / -300|-400 text), and to stay on-brand with the Signal
// design language (emerald + cyan accents, amber for finance, violet for world).
//
//   ai_tech            → emerald (brand primary; "tech")
//   business_finance   → amber   ("money")
//   world_geopolitics  → violet  (distinct, neutral-serious)
//   gulf_mena          → cyan    (brand secondary; regional)
export interface CategoryColor {
  /** Chip background + text classes. */
  chip: string;
  /** Thin left accent border class for the card. */
  accent: string;
}

export const CATEGORY_COLORS: Record<Category, CategoryColor> = {
  ai_tech: {
    chip: "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300",
    accent: "border-emerald-500 dark:border-emerald-400",
  },
  business_finance: {
    chip: "bg-amber-50 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300",
    accent: "border-amber-500 dark:border-amber-400",
  },
  world_geopolitics: {
    chip: "bg-violet-50 text-violet-700 dark:bg-violet-950/40 dark:text-violet-300",
    accent: "border-violet-500 dark:border-violet-400",
  },
  gulf_mena: {
    chip: "bg-cyan-50 text-cyan-700 dark:bg-cyan-950/40 dark:text-cyan-300",
    accent: "border-cyan-500 dark:border-cyan-400",
  },
};

// Neutral fallback for items with no category.
export const CATEGORY_FALLBACK: CategoryColor = {
  chip: "bg-muted text-muted-foreground",
  accent: "border-foreground/15",
};

export function categoryColor(category: Category | null | undefined): CategoryColor {
  if (!category) return CATEGORY_FALLBACK;
  return CATEGORY_COLORS[category] ?? CATEGORY_FALLBACK;
}
