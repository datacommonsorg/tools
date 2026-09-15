import { describe, expect, it } from "vitest";
import { isCitable, sourceLabel } from "./chip_citation";
import type { ProvenanceItem } from "../hooks/use_sse_chat";

const SOURCES: ProvenanceItem[] = [
  { name: "World Development Indicators", url: "https://worldbank.org/wdi" },
  { name: "", url: "https://oecd.org/wage-gap" },
  { name: "OECD", url: "https://oecd.org" },
];

describe("sourceLabel", () => {
  it("names the source a chip points at", () => {
    expect(sourceLabel(1, SOURCES)).toBe("World Development Indicators");
    expect(sourceLabel(3, SOURCES)).toBe("OECD");
  });

  it("is 1-based, matching the numbering SourcesList renders", () => {
    // [1] is sources[0]. Off-by-one here would label every chip with its
    // neighbour's source, which reads as correct and is not.
    expect(sourceLabel(2, SOURCES)).not.toBe("World Development Indicators");
  });

  it("falls back to the URL when the source has no name", () => {
    expect(sourceLabel(2, SOURCES)).toBe("https://oecd.org/wage-gap");
  });

  it("does not repeat itself when there is no source to name", () => {
    // sourceLabel already yields "Source n" past the end, so the aria-label
    // must not prefix it again ("Source 9: Source 9").
    expect(sourceLabel(9, SOURCES)).toBe("Source 9");
  });

  it("falls back to the bare number past the end of the list", () => {
    // The agent sometimes emits a marker before provenance has caught up.
    expect(sourceLabel(4, SOURCES)).toBe("Source 4");
    expect(sourceLabel(1, [])).toBe("Source 1");
    expect(sourceLabel(1, undefined)).toBe("Source 1");
  });
});

describe("isCitable", () => {
  it("accepts every number the Sources list actually renders", () => {
    // The whole numbering contract: [n] is row n, never rewritten, so every
    // in-range marker links and no in-range source is skipped.
    expect(isCitable(1, SOURCES)).toBe(true);
    expect(isCitable(2, SOURCES)).toBe(true);
    expect(isCitable(3, SOURCES)).toBe(true);
  });

  it("rejects a number past the end of the list", () => {
    // No #source-4 anchor is emitted, so linking it produced a dead click.
    expect(isCitable(4, SOURCES)).toBe(false);
    expect(isCitable(99, SOURCES)).toBe(false);
  });

  it("rejects a non-positive number", () => {
    expect(isCitable(0, SOURCES)).toBe(false);
    expect(isCitable(-1, SOURCES)).toBe(false);
  });

  it("rejects everything when there is no provenance at all", () => {
    expect(isCitable(1, [])).toBe(false);
    expect(isCitable(1, undefined)).toBe(false);
  });
});
