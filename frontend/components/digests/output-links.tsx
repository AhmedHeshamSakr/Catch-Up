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
    <div className="flex flex-col gap-1.5">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5">
        {entries.map((key) => {
          const { label, icon: Icon } = OUTPUT_META[key];
          const path = outputs[key];
          const basename = path.split("/").pop() ?? path;

          return (
            <div
              key={key}
              className="inline-flex items-center gap-1.5 text-xs text-muted-foreground"
            >
              <Icon className="size-3 shrink-0" aria-hidden="true" />
              <span className="font-medium text-foreground">{label}</span>
              <span className="font-mono tabular-nums">{basename}</span>
            </div>
          );
        })}
      </div>
      <p className="text-[11px] text-muted-foreground">
        Output files are written to the API host filesystem (not served over the
        web).
      </p>
    </div>
  );
}
