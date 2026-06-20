import { Suspense } from "react";
import { DigestsRouter } from "@/components/digests/digests-router";
import { Skeleton } from "@/components/ui/skeleton";

// useSearchParams (in DigestsRouter) must sit under a Suspense boundary or the
// static export build fails ("Missing Suspense boundary with useSearchParams").
export default function DigestsPage() {
  return (
    <Suspense fallback={<Skeleton className="h-40 rounded-xl w-full" />}>
      <DigestsRouter />
    </Suspense>
  );
}
