"use client"; // Error boundaries must be Client Components

import { PageHeader } from "@/components/layout/page-header";
import { ErrorState } from "@/components/common/error-state";
import { Card, CardContent } from "@/components/ui/card";

// Next.js 16 renamed the recovery prop to `unstable_retry`; `reset` is the
// legacy name. Accept either so the "Try again" button works across versions.
interface RouteErrorProps {
  error: Error & { digest?: string };
  unstable_retry?: () => void;
  reset?: () => void;
}

export default function RouteError({
  error,
  unstable_retry,
  reset,
}: RouteErrorProps) {
  const retry = unstable_retry ?? reset;

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Something went wrong"
        subtitle="An unexpected error occurred while rendering this page"
      />
      <Card>
        <CardContent className="py-0">
          <ErrorState
            title="This page hit an error"
            description={
              error?.message ||
              "Try again, or head back to the dashboard if it persists."
            }
            onRetry={retry ? () => retry() : undefined}
          />
        </CardContent>
      </Card>
    </div>
  );
}
