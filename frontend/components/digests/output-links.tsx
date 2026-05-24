import { Globe, Sheet, FileText } from "lucide-react";
import type { LucideIcon } from "lucide-react";

interface OutputLinksProps {
  outputs: Record<string, string>;
}

type OutputKey = "html" | "excel" | "markdown";

const OUTPUT_ORDER: OutputKey[] = ["html", "excel", "markdown"];

const OUTPUT_META: Record<OutputKey, { label: string; icon: LucideIcon }> = {
  html: { label: "HTML", icon: Globe },
  excel: { label: "Excel", icon: Sheet },
  markdown: { label: "Markdown", icon: FileText },
};

export function OutputLinks({ outputs }: OutputLinksProps) {
  const entries = OUTPUT_ORDER.filter((key) => key in outputs);

  if (entries.length === 0) return null;

  return (
    <div className="flex flex-wrap items-center gap-2">
      {entries.map((key) => {
        const { label, icon: Icon } = OUTPUT_META[key];
        const path = outputs[key];
        const basename = path.split("/").pop() ?? path;

        return (
          <div
            key={key}
            title="Available on the API host filesystem"
            className="inline-flex items-center gap-1.5 rounded-full bg-muted px-3 py-1 text-xs text-muted-foreground"
          >
            <Icon className="size-3 shrink-0" aria-hidden="true" />
            <span className="font-medium text-foreground">{label}</span>
            <span className="font-mono tabular-nums">{basename}</span>
          </div>
        );
      })}
    </div>
  );
}
