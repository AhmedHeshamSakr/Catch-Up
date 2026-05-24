import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AsyncBoundary } from "@/components/common/async-boundary";
import { describe, it, expect, vi } from "vitest";

describe("AsyncBoundary", () => {
  it("renders the skeleton while loading", () => {
    render(
      <AsyncBoundary
        isLoading
        error={undefined}
        skeleton={<div>loading-skeleton</div>}
      >
        <div>data-view</div>
      </AsyncBoundary>
    );
    expect(screen.getByText("loading-skeleton")).toBeInTheDocument();
    expect(screen.queryByText("data-view")).not.toBeInTheDocument();
  });

  it("renders the error state and calls onRetry on retry click", async () => {
    const user = userEvent.setup();
    const onRetry = vi.fn();
    render(
      <AsyncBoundary
        isLoading={false}
        error={new Error("boom")}
        skeleton={<div>loading-skeleton</div>}
        onRetry={onRetry}
        errorTitle="Couldn't load"
      >
        <div>data-view</div>
      </AsyncBoundary>
    );
    expect(screen.getByText("Couldn't load")).toBeInTheDocument();
    expect(screen.queryByText("data-view")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("renders the empty slot when isEmpty is true", () => {
    render(
      <AsyncBoundary
        isLoading={false}
        error={undefined}
        isEmpty
        skeleton={<div>loading-skeleton</div>}
        empty={<div>nothing-here</div>}
      >
        <div>data-view</div>
      </AsyncBoundary>
    );
    expect(screen.getByText("nothing-here")).toBeInTheDocument();
    expect(screen.queryByText("data-view")).not.toBeInTheDocument();
  });

  it("renders children when data is present", () => {
    render(
      <AsyncBoundary
        isLoading={false}
        error={undefined}
        isEmpty={false}
        skeleton={<div>loading-skeleton</div>}
        empty={<div>nothing-here</div>}
      >
        <div>data-view</div>
      </AsyncBoundary>
    );
    expect(screen.getByText("data-view")).toBeInTheDocument();
    expect(screen.queryByText("loading-skeleton")).not.toBeInTheDocument();
    expect(screen.queryByText("nothing-here")).not.toBeInTheDocument();
  });
});
