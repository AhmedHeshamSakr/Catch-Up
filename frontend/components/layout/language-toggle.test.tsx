import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, beforeEach } from "vitest";
import { LanguageToggle } from "@/components/layout/language-toggle";

beforeEach(() => {
  window.localStorage.clear();
});

describe("LanguageToggle", () => {
  it("renders both options with EN active by default", () => {
    render(<LanguageToggle />);
    const en = screen.getByRole("button", { name: "EN" });
    const ar = screen.getByRole("button", { name: "العربية" });
    expect(en).toHaveAttribute("aria-pressed", "true");
    expect(ar).toHaveAttribute("aria-pressed", "false");
  });

  it("exposes an accessible group label", () => {
    render(<LanguageToggle />);
    expect(
      screen.getByRole("group", { name: "Display language" })
    ).toBeInTheDocument();
  });

  it("clicking AR sets aria-pressed on AR and persists the choice", async () => {
    const user = userEvent.setup();
    render(<LanguageToggle />);
    await user.click(screen.getByRole("button", { name: "العربية" }));
    expect(screen.getByRole("button", { name: "العربية" })).toHaveAttribute(
      "aria-pressed",
      "true"
    );
    expect(screen.getByRole("button", { name: "EN" })).toHaveAttribute(
      "aria-pressed",
      "false"
    );
    expect(window.localStorage.getItem("catchup.lang")).toBe("ar");
  });
});
