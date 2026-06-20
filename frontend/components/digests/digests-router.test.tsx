import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";

const mockGet = vi.fn();
vi.mock("next/navigation", () => ({
  useSearchParams: () => ({ get: mockGet }),
}));
vi.mock("@/components/digests/run-detail", () => ({
  RunDetail: ({ runId }: { runId: string }) => <div>detail:{runId}</div>,
}));
vi.mock("@/components/digests/runs-list", () => ({
  RunsList: () => <div>runs-list</div>,
}));

import { DigestsRouter } from "@/components/digests/digests-router";

describe("DigestsRouter", () => {
  it("renders the run detail when ?run= is present", () => {
    mockGet.mockReturnValue("run-xyz");
    render(<DigestsRouter />);
    expect(screen.getByText("detail:run-xyz")).toBeInTheDocument();
  });

  it("renders the runs list when there is no run param", () => {
    mockGet.mockReturnValue(null);
    render(<DigestsRouter />);
    expect(screen.getByText("runs-list")).toBeInTheDocument();
  });
});
