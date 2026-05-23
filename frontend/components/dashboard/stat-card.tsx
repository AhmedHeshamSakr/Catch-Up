import type { ReactNode, ComponentType } from "react";
import type { LucideProps } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface StatCardProps {
  label: string;
  value: ReactNode;
  icon?: ComponentType<LucideProps>;
  hint?: string;
  className?: string;
}

export function StatCard({ label, value, icon: Icon, hint, className }: StatCardProps) {
  return (
    <Card className={cn("relative", className)}>
      <CardContent className="flex flex-col gap-2 pt-1">
        <div className="flex items-start justify-between">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
            {label}
          </p>
          {Icon && (
            <Icon
              className="h-4 w-4 text-muted-foreground/60 shrink-0"
              aria-hidden="true"
            />
          )}
        </div>
        <div className="text-2xl font-mono tabular-nums font-semibold text-foreground leading-none">
          {value}
        </div>
        {hint && (
          <p className="text-xs text-muted-foreground">{hint}</p>
        )}
      </CardContent>
    </Card>
  );
}
