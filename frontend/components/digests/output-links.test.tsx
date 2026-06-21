import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { OutputLinks } from "@/components/digests/output-links";

describe("OutputLinks", () => {
  // Backend writes run.outputs with the keys md / xlsx / html
  // (app/pipeline/agents.py RenderAgent). All three must render.
  const outputs = {
    md: "/out/digest-abc.md",
    xlsx: "/out/digest-abc.xlsx",
    html: "/out/digest-abc.html",
  };

  it("renders a badge for each backend output key", () => {
    render(<OutputLinks outputs={outputs} />);
    expect(screen.getByText("HTML")).toBeInTheDocument();
    expect(screen.getByText("Excel")).toBeInTheDocument();
    expect(screen.getByText("Markdown")).toBeInTheDocument();
    expect(screen.getByText("digest-abc.xlsx")).toBeInTheDocument();
    expect(screen.getByText("digest-abc.md")).toBeInTheDocument();
  });

  it("renders nothing when there are no recognized outputs", () => {
    const { container } = render(<OutputLinks outputs={{}} />);
    expect(container).toBeEmptyDOMElement();
  });
});
