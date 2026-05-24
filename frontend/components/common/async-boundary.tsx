"use client";

// -----------------------------------------------------------------------
// AsyncBoundary
//
// Rendering decision (intentional): the Catch-Up Console is a client-rendered
// SWR app. It is an internal tool where live revalidation of agent runs beats
// SSR, so every page is a Client Component fetching via SWR. Route-level
// `app/error.tsx` and `app/not-found.tsx` boundaries cover unexpected failures
// and unmatched URLs; this AsyncBoundary DRYs the per-page
// loading -> error -> empty -> data ladder that the SWR `{ data, error,
// isLoading }` shape produces.
//
// Presentational and side-effect-free (NO useEffect) — the caller owns data
// fetching and decides `isLoading`/`isEmpty` from its own SWR state.
// -----------------------------------------------------------------------

import type { ReactNode } from "react";
import { ErrorState } from "@/components/common/error-state";
import { Card, CardContent } from "@/components/ui/card";

interface AsyncBoundaryProps {
  isLoading: boolean;
  error: unknown;
  isEmpty?: boolean;
  /** Shown while loading with no data yet. */
  skeleton: ReactNode;
  /** Shown when `isEmpty` is true. */
  empty?: ReactNode;
  /** Wires the ErrorState retry button. */
  onRetry?: () => void;
  /** Title for the fallback error state. */
  errorTitle?: string;
  /** Description for the fallback error state. */
  errorDescription?: string;
  /** The data view. */
  children: ReactNode;
}

export function AsyncBoundary({
  isLoading,
  error,
  isEmpty = false,
  skeleton,
  empty = null,
  onRetry,
  errorTitle,
  errorDescription,
  children,
}: AsyncBoundaryProps) {
  // Error wins only when we are not actively loading (the caller passes
  // `isLoading` already gated on "no data yet", matching SWR semantics).
  // The ErrorState is Card-wrapped to match the per-page error visuals it
  // replaces.
  if (error && !isLoading) {
    return (
      <Card>
        <CardContent className="py-0">
          <ErrorState
            title={errorTitle}
            description={errorDescription}
            onRetry={onRetry}
          />
        </CardContent>
      </Card>
    );
  }

  if (isLoading) {
    return <>{skeleton}</>;
  }

  if (isEmpty) {
    return <>{empty}</>;
  }

  return <>{children}</>;
}
