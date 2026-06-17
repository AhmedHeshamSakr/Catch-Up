import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { RunNowButton } from "@/components/layout/run-now-button";
import { api, ApiError } from "@/lib/api";

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));
import { toast } from "sonner";

beforeEach(() => {
  vi.clearAllMocks();
});

describe("RunNowButton", () => {
  it("surfaces the returned run_id in the success toast", async () => {
    vi.spyOn(api, "triggerRun").mockResolvedValue({ status: "started", run_id: "abc123def456" });
    const user = userEvent.setup();
    render(<RunNowButton />);
    await user.click(screen.getByRole("button", { name: /run now/i }));
    expect(toast.success).toHaveBeenCalledWith(
      "Digest run started",
      expect.objectContaining({ description: expect.stringContaining("abc123de") })
    );
  });

  it("shows a distinct message on 409 (a run already in progress)", async () => {
    vi.spyOn(api, "triggerRun").mockRejectedValue(
      new ApiError(409, "a digest run is already in progress")
    );
    const user = userEvent.setup();
    render(<RunNowButton />);
    await user.click(screen.getByRole("button", { name: /run now/i }));
    expect(toast.error).toHaveBeenCalledWith(
      "A digest run is already in progress",
      expect.objectContaining({ description: expect.any(String) })
    );
  });
});
