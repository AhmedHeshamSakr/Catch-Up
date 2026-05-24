import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { CATEGORY_LABELS } from "@/lib/labels";
import type { Category } from "@/lib/types";

const CATEGORY_ORDER: Category[] = [
  "ai_tech",
  "business_finance",
  "world_geopolitics",
  "gulf_mena",
];

interface CategoryBreakdownProps {
  counts: Record<string, number>;
}

export function CategoryBreakdown({ counts }: CategoryBreakdownProps) {
  const values = CATEGORY_ORDER.map((cat) => counts[cat] ?? 0);
  const maxCount = Math.max(...values, 1);
  const allZero = values.every((v) => v === 0);

  return (
    <Card>
      <CardHeader>
        <CardTitle>By category</CardTitle>
      </CardHeader>
      <CardContent>
        {allZero ? (
          <p className="text-xs text-muted-foreground">No categorized items yet.</p>
        ) : (
          <div className="flex flex-col gap-3">
            {CATEGORY_ORDER.map((cat, i) => {
              const count = values[i];
              const pct = Math.round((count / maxCount) * 100);
              return (
                <div key={cat} className="flex flex-col gap-1">
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-foreground">{CATEGORY_LABELS[cat]}</span>
                    <span className="text-xs font-mono tabular-nums text-muted-foreground">
                      {count}
                    </span>
                  </div>
                  <div className="h-1.5 w-full rounded-full bg-muted overflow-hidden">
                    <div
                      className="h-full rounded-full bg-emerald transition-all duration-300"
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
