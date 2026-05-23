import { describe, it, expect } from "vitest";
import { addTag } from "@/lib/tags";

describe("addTag", () => {
  it("adds a trimmed tag", () => {
    expect(addTag(["a"], "  b ")).toEqual(["a", "b"]);
  });
  it("ignores blank", () => {
    expect(addTag(["a"], "   ")).toEqual(["a"]);
  });
  it("dedupes case-insensitively", () => {
    expect(addTag(["OpenAI"], "openai")).toEqual(["OpenAI"]);
  });
});
