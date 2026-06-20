import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
import { toast } from "sonner";
import { api } from "@/lib/api";
import SettingsPage from "@/app/settings/page";

beforeEach(() => {
  vi.clearAllMocks();
  vi.spyOn(api, "getSettings").mockResolvedValue({
    app_host: "127.0.0.1",
    app_port: 8000,
    gemini_key_set: true,
  });
  vi.spyOn(api, "putSettings").mockResolvedValue({
    applied: ["google_api_key"],
    restart_required: [],
  });
});

describe("SettingsPage", () => {
  it("shows the key-configured indicator from loaded state", async () => {
    render(<SettingsPage />);
    expect(await screen.findByText(/key configured/i)).toBeInTheDocument();
  });

  it("saves a newly entered Gemini key via putSettings", async () => {
    const user = userEvent.setup();
    render(<SettingsPage />);
    await screen.findByText(/key configured/i);
    await user.type(screen.getByLabelText(/gemini api key/i), "new-key-123");
    await user.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() =>
      expect(api.putSettings).toHaveBeenCalledWith(
        expect.objectContaining({ google_api_key: "new-key-123" })
      )
    );
    expect(toast.success).toHaveBeenCalled();
  });

  it("saves a changed port", async () => {
    vi.spyOn(api, "putSettings").mockResolvedValue({
      applied: [],
      restart_required: ["app_port"],
    });
    const user = userEvent.setup();
    render(<SettingsPage />);
    await screen.findByText(/key configured/i);
    const port = screen.getByLabelText(/port/i);
    await user.clear(port);
    await user.type(port, "9000");
    await user.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() =>
      expect(api.putSettings).toHaveBeenCalledWith(
        expect.objectContaining({ app_port: 9000 })
      )
    );
  });

  it("does not resend an unchanged port or empty key", async () => {
    const user = userEvent.setup();
    render(<SettingsPage />);
    await screen.findByText(/key configured/i);
    await user.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() => expect(api.putSettings).toHaveBeenCalled());
    const arg = vi.mocked(api.putSettings).mock.calls[0][0];
    expect(arg.google_api_key).toBeUndefined();
    expect(arg.app_port).toBeUndefined();
  });
});
