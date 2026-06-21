import { render, screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, beforeEach } from "vitest";
import { NewsCard } from "@/components/digests/news-card";
import type { NewsItem } from "@/lib/types";

function makeItem(overrides: Partial<NewsItem> = {}): NewsItem {
  return {
    id: "1",
    org_id: "o",
    user_id: "u",
    source_id: "s",
    source_type: "rss",
    source_name: "Acme News",
    url: "https://example.com/article",
    title: "Headline goes here",
    excerpt: "An excerpt fallback.",
    published_at: "2026-05-01T00:00:00Z",
    collected_at: "2026-05-01T00:00:00Z",
    category: "ai_tech",
    summary_en: "English takeaway summary.",
    summary_ar: "ملخص عربي للخبر.",
    importance: "high",
    importance_score: 0.82,
    entities: [
      { name: "OpenAI", type: "org" },
      { name: "Qatar", type: "place" },
    ],
    sentiment: "positive",
    status: "ok",
    digest_run_id: null,
    ...overrides,
  };
}

beforeEach(() => {
  window.localStorage.clear();
});

describe("NewsCard", () => {
  it("shows the English takeaway by default in primary text", () => {
    render(<NewsCard item={makeItem()} />);
    const takeaway = screen.getByText("English takeaway summary.");
    expect(takeaway).toBeInTheDocument();
    expect(takeaway).toHaveAttribute("lang", "en");
    // Arabic summary is not shown in the default (collapsed) view.
    expect(screen.queryByText("ملخص عربي للخبر.")).not.toBeInTheDocument();
  });

  it("shows the Arabic takeaway RTL when the language preference is ar", () => {
    window.localStorage.setItem("catchup.lang", "ar");
    render(<NewsCard item={makeItem()} />);
    const takeaway = screen.getByText("ملخص عربي للخبر.");
    expect(takeaway).toBeInTheDocument();
    expect(takeaway).toHaveAttribute("dir", "rtl");
    expect(takeaway).toHaveAttribute("lang", "ar");
  });

  it("falls back to the other language when the preferred is missing", () => {
    window.localStorage.setItem("catchup.lang", "ar");
    render(<NewsCard item={makeItem({ summary_ar: null })} />);
    expect(screen.getByText("English takeaway summary.")).toBeInTheDocument();
  });

  it("falls back to the excerpt when both summaries are missing", () => {
    render(
      <NewsCard item={makeItem({ summary_en: null, summary_ar: null })} />
    );
    expect(screen.getByText("An excerpt fallback.")).toBeInTheDocument();
  });

  it("renders a thumbnail for a valid https image_url", () => {
    render(
      <NewsCard
        item={makeItem({ image_url: "https://cdn.example.com/pic.jpg" })}
      />
    );
    const img = screen.getByRole("img", { name: "Headline goes here" });
    expect(img).toHaveAttribute("src", "https://cdn.example.com/pic.jpg");
    expect(img).toHaveAttribute("loading", "lazy");
  });

  it("does not render a thumbnail when image_url is null or empty", () => {
    const { rerender } = render(
      <NewsCard item={makeItem({ image_url: null })} />
    );
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    rerender(<NewsCard item={makeItem({ image_url: "" })} />);
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });

  it("does not render a thumbnail for a non-http(s) image_url", () => {
    render(
      <NewsCard
        item={makeItem({ image_url: "data:image/png;base64,AAAA" })}
      />
    );
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });

  it("hides the thumbnail after the image fails to load", () => {
    render(
      <NewsCard
        item={makeItem({ image_url: "https://cdn.example.com/broken.jpg" })}
      />
    );
    fireEvent.error(screen.getByRole("img"));
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });

  it("toggles aria-expanded and reveals entities, other-language and score", async () => {
    const user = userEvent.setup();
    render(<NewsCard item={makeItem()} />);

    const toggle = screen.getByRole("button", { name: /details/i });
    expect(toggle).toHaveAttribute("aria-expanded", "false");

    // Hidden before expanding.
    expect(screen.queryByText("OpenAI")).not.toBeInTheDocument();
    expect(screen.queryByText("ملخص عربي للخبر.")).not.toBeInTheDocument();
    expect(screen.queryByText(/Importance score/i)).not.toBeInTheDocument();

    await user.click(toggle);

    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("OpenAI")).toBeInTheDocument();
    expect(screen.getByText("Qatar")).toBeInTheDocument();
    expect(screen.getByText("ملخص عربي للخبر.")).toBeInTheDocument();
    expect(screen.getByText(/Importance score/i)).toBeInTheDocument();
  });

  it("links the headline to the source url", () => {
    render(<NewsCard item={makeItem()} />);
    const link = screen.getByRole("link", { name: "Headline goes here" });
    expect(link).toHaveAttribute("href", "https://example.com/article");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
  });
});
