"use client";

import { useLanguage, type Lang } from "@/lib/use-language";
import { cn } from "@/lib/utils";

const OPTIONS: { value: Lang; label: string }[] = [
  { value: "en", label: "EN" },
  { value: "ar", label: "العربية" },
];

export function LanguageToggle() {
  const { lang, setLang } = useLanguage();

  return (
    <div
      role="group"
      aria-label="Display language"
      className="inline-flex items-center gap-0.5 rounded-lg border border-border bg-muted/40 p-0.5"
    >
      {OPTIONS.map(({ value, label }) => {
        const active = lang === value;
        return (
          <button
            key={value}
            type="button"
            aria-pressed={active}
            onClick={() => setLang(value)}
            className={cn(
              "rounded-[min(var(--radius-md),10px)] px-2 py-0.5 text-xs font-medium transition-colors outline-none focus-visible:ring-2 focus-visible:ring-ring",
              active
                ? "bg-primary text-primary-foreground"
                : "text-muted-foreground hover:text-foreground"
            )}
          >
            {label}
          </button>
        );
      })}
    </div>
  );
}
