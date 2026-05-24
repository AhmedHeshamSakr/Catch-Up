import { render, screen } from "@testing-library/react";
import { ImportanceBadge } from "@/components/common/importance-badge";
import { describe, it, expect } from "vitest";

describe("ImportanceBadge", () => {
  it("renders High label for high importance", () => {
    render(<ImportanceBadge importance="high" />);
    expect(screen.getByText("High")).toBeInTheDocument();
  });
  it("renders nothing for null", () => {
    const { container } = render(<ImportanceBadge importance={null} />);
    expect(container).toBeEmptyDOMElement();
  });
});
