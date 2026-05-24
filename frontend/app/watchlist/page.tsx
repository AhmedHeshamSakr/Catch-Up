"use client";

import { useState } from "react";
import { toast } from "sonner";
import { useWatchlist } from "@/lib/hooks";
import { api, ApiError } from "@/lib/api";
import type { Watchlist } from "@/lib/types";
import { PageHeader } from "@/components/layout/page-header";
import { ErrorState } from "@/components/common/error-state";
import { TagEditor } from "@/components/watchlist/tag-editor";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

// -----------------------------------------------------------------------
// Inner editor — mounted fresh each time data loads (key-based seed).
// useState(initial) initialises from props once with no effect needed.
// -----------------------------------------------------------------------
interface WatchlistEditorProps {
  initial: Watchlist;
  onSaved: () => void;
}

function WatchlistEditor({ initial, onSaved }: WatchlistEditorProps) {
  const [entities, setEntities] = useState<string[]>(initial.entities);
  const [keywords, setKeywords] = useState<string[]>(initial.keywords);
  const [saving, setSaving] = useState(false);

  const dirty =
    JSON.stringify(entities) !== JSON.stringify(initial.entities) ||
    JSON.stringify(keywords) !== JSON.stringify(initial.keywords);

  async function handleSave() {
    setSaving(true);
    try {
      await api.putWatchlist({ entities, keywords });
      toast.success("Watchlist saved");
      onSaved();
    } catch (err) {
      const msg =
        err instanceof ApiError ? err.message : "Failed to save watchlist";
      toast.error(msg);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <Card>
        <CardHeader>
          <CardTitle>Entities</CardTitle>
        </CardHeader>
        <CardContent>
          <TagEditor
            label="Companies & people"
            description="Matches boost an item's importance score by +0.25."
            values={entities}
            onChange={setEntities}
            placeholder="Add company or person..."
            inputId="watchlist-entities"
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Keywords</CardTitle>
        </CardHeader>
        <CardContent>
          <TagEditor
            label="Keywords"
            description="Matches boost an item's importance score by +0.25."
            values={keywords}
            onChange={setKeywords}
            placeholder="Add keyword..."
            inputId="watchlist-keywords"
          />
        </CardContent>
      </Card>

      <div className="flex items-center justify-between">
        {dirty ? (
          <p className="text-xs text-muted-foreground">Unsaved changes</p>
        ) : (
          <span />
        )}
        <Button onClick={handleSave} disabled={!dirty || saving}>
          {saving ? "Saving..." : "Save changes"}
        </Button>
      </div>
    </div>
  );
}

// -----------------------------------------------------------------------
// Skeleton shown while data is loading
// -----------------------------------------------------------------------
function WatchlistSkeleton() {
  return (
    <div className="flex flex-col gap-6">
      {[0, 1].map((i) => (
        <Card key={i}>
          <CardHeader>
            <Skeleton className="h-5 w-24" />
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            <Skeleton className="h-4 w-48" />
            <div className="flex flex-wrap gap-1.5">
              {[0, 1, 2].map((j) => (
                <Skeleton key={j} className="h-6 w-20 rounded-full" />
              ))}
            </div>
            <Skeleton className="h-8 w-full" />
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

// -----------------------------------------------------------------------
// Page
// -----------------------------------------------------------------------
export default function WatchlistPage() {
  const { data, error, isLoading, mutate } = useWatchlist();

  // A stable key tied to the loaded data so WatchlistEditor resets
  // its internal draft state whenever we call mutate() after a save.
  const [savedCount, setSavedCount] = useState(0);

  function handleSaved() {
    mutate();
    setSavedCount((c) => c + 1);
  }

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Watchlist"
        subtitle="Entities and keywords that boost importance"
      />

      {isLoading && !data && <WatchlistSkeleton />}

      {error && !data && (
        <Card>
          <CardContent className="py-0">
            <ErrorState
              title="Couldn't load watchlist"
              description="Is the API running on :8000?"
              onRetry={() => mutate()}
            />
          </CardContent>
        </Card>
      )}

      {data && (
        <WatchlistEditor
          key={`watchlist-${savedCount}`}
          initial={data}
          onSaved={handleSaved}
        />
      )}
    </div>
  );
}
