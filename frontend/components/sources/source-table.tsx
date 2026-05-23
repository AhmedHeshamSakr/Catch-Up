"use client";

import { Pencil, Trash2 } from "lucide-react";
import {
  Table,
  TableHeader,
  TableBody,
  TableHead,
  TableRow,
  TableCell,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import type { SourceConfig } from "@/lib/types";
import { CATEGORY_LABELS, SOURCE_TYPE_LABELS } from "@/lib/labels";

interface SourceTableProps {
  sources: SourceConfig[];
  onEdit: (s: SourceConfig) => void;
  onDelete: (s: SourceConfig) => void;
  onToggle: (s: SourceConfig, enabled: boolean) => void;
}

function typeVariant(
  type: SourceConfig["type"]
): "default" | "secondary" | "outline" {
  switch (type) {
    case "rss":
      return "default";
    case "scrape":
      return "secondary";
    case "api":
      return "outline";
    case "search":
      return "outline";
  }
}

function sourceTarget(s: SourceConfig): string {
  return s.url ?? s.query ?? s.selector ?? "—";
}

export function SourceTable({
  sources,
  onEdit,
  onDelete,
  onToggle,
}: SourceTableProps) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Name</TableHead>
          <TableHead>Type</TableHead>
          <TableHead>Category</TableHead>
          <TableHead>Target</TableHead>
          <TableHead>Enabled</TableHead>
          <TableHead className="w-20 text-right">Actions</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {sources.map((source) => {
          const target = sourceTarget(source);
          const showTarget = target !== "—";

          return (
            <TableRow key={source.id}>
              <TableCell>
                <div className="flex flex-col gap-0.5">
                  <span className="font-medium text-foreground">
                    {source.name}
                  </span>
                  <span className="font-mono text-[11px] text-muted-foreground">
                    {source.id}
                  </span>
                </div>
              </TableCell>
              <TableCell>
                <Badge variant={typeVariant(source.type)}>
                  {SOURCE_TYPE_LABELS[source.type]}
                </Badge>
              </TableCell>
              <TableCell>
                <span className="text-sm text-muted-foreground">
                  {source.category_hint
                    ? CATEGORY_LABELS[source.category_hint]
                    : "—"}
                </span>
              </TableCell>
              <TableCell className="max-w-[220px]">
                {showTarget ? (
                  <span className="block truncate font-mono text-xs text-muted-foreground">
                    {target}
                  </span>
                ) : (
                  <span className="text-sm text-muted-foreground">—</span>
                )}
              </TableCell>
              <TableCell>
                <Switch
                  checked={source.enabled}
                  onCheckedChange={(checked) => onToggle(source, checked)}
                  aria-label={`${source.enabled ? "Disable" : "Enable"} ${source.name}`}
                />
              </TableCell>
              <TableCell>
                <div className="flex items-center justify-end gap-1">
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    onClick={() => onEdit(source)}
                    aria-label={`Edit ${source.name}`}
                  >
                    <Pencil />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    onClick={() => onDelete(source)}
                    aria-label={`Delete ${source.name}`}
                    className="text-destructive hover:text-destructive hover:bg-destructive/10"
                  >
                    <Trash2 />
                  </Button>
                </div>
              </TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}
