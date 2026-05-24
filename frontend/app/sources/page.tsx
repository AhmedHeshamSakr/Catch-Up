"use client";

import { useState } from "react";
import { Plus, Rss } from "lucide-react";
import { toast } from "sonner";
import { useSources } from "@/lib/hooks";
import { api, ApiError } from "@/lib/api";
import type { SourceConfig } from "@/lib/types";
import { PageHeader } from "@/components/layout/page-header";
import { EmptyState } from "@/components/common/empty-state";
import { AsyncBoundary } from "@/components/common/async-boundary";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Card, CardContent } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { SourceTable } from "@/components/sources/source-table";
import { SourceFormDialog } from "@/components/sources/source-form-dialog";

function SourcesSkeleton() {
  return (
    <div className="flex flex-col gap-2">
      {Array.from({ length: 4 }).map((_, i) => (
        <Skeleton key={i} className="h-14 rounded-xl w-full" />
      ))}
    </div>
  );
}

export default function SourcesPage() {
  const { data: sources, error, isLoading, mutate } = useSources();

  // Dialog state
  const [formOpen, setFormOpen] = useState(false);
  const [editingSource, setEditingSource] = useState<SourceConfig | null>(null);

  // Delete confirm dialog state
  const [deleteTarget, setDeleteTarget] = useState<SourceConfig | null>(null);
  const [deleting, setDeleting] = useState(false);

  function openAdd() {
    setEditingSource(null);
    setFormOpen(true);
  }

  function openEdit(source: SourceConfig) {
    setEditingSource(source);
    setFormOpen(true);
  }

  function openDelete(source: SourceConfig) {
    setDeleteTarget(source);
  }

  async function handleSave(s: SourceConfig) {
    const current = sources ?? [];
    const next = editingSource
      ? current.map((src) => (src.id === s.id ? s : src))
      : [...current, s];

    try {
      await api.putSources(next);
      toast.success(
        editingSource
          ? `Source "${s.name}" updated`
          : `Source "${s.name}" added`
      );
      mutate(next);
    } catch (err) {
      const msg =
        err instanceof ApiError ? err.message : "Failed to save source";
      toast.error(msg);
      throw err; // keep dialog open
    }
  }

  async function handleToggle(source: SourceConfig, enabled: boolean) {
    const current = sources ?? [];
    const next = current.map((src) =>
      src.id === source.id ? { ...src, enabled } : src
    );

    // Optimistic update
    mutate(next, false);

    try {
      await api.putSources(next);
    } catch (err) {
      const msg =
        err instanceof ApiError ? err.message : "Failed to update source";
      toast.error(msg);
      mutate(); // revert
    }
  }

  async function handleDelete() {
    if (!deleteTarget) return;
    const current = sources ?? [];
    const next = current.filter((src) => src.id !== deleteTarget.id);

    setDeleting(true);
    try {
      await api.putSources(next);
      toast.success(`Source "${deleteTarget.name}" deleted`);
      mutate(next);
      setDeleteTarget(null);
    } catch (err) {
      const msg =
        err instanceof ApiError ? err.message : "Failed to delete source";
      toast.error(msg);
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Sources"
        subtitle="Where Catch-Up collects news"
        actions={
          <Button onClick={openAdd}>
            <Plus />
            Add source
          </Button>
        }
      />

      <AsyncBoundary
        isLoading={isLoading && !sources}
        error={error && !sources ? error : undefined}
        isEmpty={!!sources && sources.length === 0}
        onRetry={() => mutate()}
        errorTitle="Couldn't load sources"
        errorDescription="Is the API running on :8000?"
        skeleton={<SourcesSkeleton />}
        empty={
          <Card>
            <CardContent className="py-0">
              <EmptyState
                icon={Rss}
                title="No sources yet"
                description="Add your first news source to start collecting."
                action={
                  <Button onClick={openAdd}>
                    <Plus />
                    Add source
                  </Button>
                }
              />
            </CardContent>
          </Card>
        }
      >
        {sources && sources.length > 0 && (
          <Card>
            <CardContent className="py-0 px-0">
              <SourceTable
                sources={sources}
                onEdit={openEdit}
                onDelete={openDelete}
                onToggle={handleToggle}
              />
            </CardContent>
          </Card>
        )}
      </AsyncBoundary>

      {/* Add / Edit dialog */}
      <SourceFormDialog
        open={formOpen}
        onOpenChange={setFormOpen}
        source={editingSource}
        existingIds={(sources ?? []).map((s) => s.id)}
        onSave={handleSave}
      />

      {/* Delete confirm dialog */}
      <Dialog
        open={deleteTarget !== null}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete source</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            Are you sure you want to delete{" "}
            <span className="font-medium text-foreground">
              {deleteTarget?.name}
            </span>
            ? This cannot be undone.
          </p>
          <DialogFooter showCloseButton>
            <Button
              variant="destructive"
              onClick={handleDelete}
              disabled={deleting}
            >
              {deleting ? "Deleting..." : "Delete"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
