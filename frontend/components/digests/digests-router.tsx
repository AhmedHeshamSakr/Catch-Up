"use client";

import { useSearchParams } from "next/navigation";
import { RunsList } from "@/components/digests/runs-list";
import { RunDetail } from "@/components/digests/run-detail";

/**
 * Query-param router for the digests route. ``/digests`` shows the runs list;
 * ``/digests?run=<id>`` drills into a single run. Using a query param (instead of
 * a ``[runId]`` dynamic segment) keeps the route statically exportable.
 */
export function DigestsRouter() {
  const runId = useSearchParams().get("run");
  return runId ? <RunDetail runId={runId} /> : <RunsList />;
}
