import { describe, expect, it, beforeEach } from "vitest";
import { place, type Box } from "./tooltip";

const VIEWPORT = { width: 1000, height: 800 };

beforeEach(() => {
  window.innerWidth = VIEWPORT.width;
  window.innerHeight = VIEWPORT.height;
});

/** Builds a Box the way a DOMRect would report it. */
function box(left: number, top: number, width: number, height: number): Box {
  return { left, top, width, height, right: left + width, bottom: top + height };
}

const TIP = box(0, 0, 80, 24);

describe("place", () => {
  it("puts the tooltip above the anchor, gap of 4, centred", () => {
    const anchor = box(500, 400, 40, 40);
    expect(place(anchor, TIP, "top")).toEqual({
      top: 400 - 24 - 4,
      left: 500 + 20 - 40,
    });
  });

  it("puts it to the right, gap of 4, centred on the anchor's middle", () => {
    const anchor = box(12, 400, 48, 48);
    expect(place(anchor, TIP, "right")).toEqual({
      top: 400 + 24 - 12,
      left: 12 + 48 + 4,
    });
  });

  it("flips to the opposite side when the preferred one is clipped", () => {
    // A rail icon near the top has no room above, so "top" must become
    // "bottom" rather than render off the top of the window.
    const anchor = box(500, 10, 40, 40);
    expect(place(anchor, TIP, "top").top).toBe(10 + 40 + 4);
  });

  it("keeps the preferred side when neither side has room", () => {
    // A tooltip taller than the space either way should not thrash; it stays
    // put and gets clamped into the viewport instead.
    const anchor = box(500, 0, 40, VIEWPORT.height);
    const tall = box(0, 0, 80, 400);
    const { top } = place(anchor, tall, "top");
    expect(top).toBeGreaterThanOrEqual(8);
    expect(top + 400).toBeLessThanOrEqual(VIEWPORT.height);
  });

  it("puts it below the anchor, gap of 4, centred on the anchor's middle", () => {
    const anchor = box(500, 200, 40, 40);
    expect(place(anchor, TIP, "bottom")).toEqual({
      top: 200 + 40 + 4,
      left: 500 + 20 - 40,
    });
  });

  it("puts it to the left, gap of 4, centred on the anchor's middle", () => {
    const anchor = box(400, 400, 48, 48);
    expect(place(anchor, TIP, "left")).toEqual({
      top: 400 + 24 - 12,
      left: 400 - 80 - 4,
    });
  });

  it("positions M3 rich tooltip with larger dimensions and clamps properly", () => {
    const richTip = box(0, 0, 260, 96);
    const anchor = box(500, 200, 48, 48);
    const coords = place(anchor, richTip, "bottom");
    expect(coords.top).toBe(200 + 48 + 4);
    expect(coords.left).toBe(500 + 24 - 130);
  });

  it("clamps horizontally so an edge control's tooltip stays on screen", () => {
    // Centring on an anchor in the corner would push the tooltip negative.
    const anchor = box(0, 400, 20, 20);
    expect(place(anchor, TIP, "top").left).toBe(8);
  });

  it("clamps against the far edge too", () => {
    const anchor = box(VIEWPORT.width - 20, 400, 20, 20);
    expect(place(anchor, TIP, "top").left).toBe(VIEWPORT.width - 80 - 8);
  });
});
