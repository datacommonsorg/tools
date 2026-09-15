/**
 * @fileoverview Tests for the PDF export's layout arithmetic.
 *
 * These two functions decide whether a chart is cropped at the page edge and
 * whether one is sliced in half by a page break — both reported as bugs against
 * exported PDFs, and both awkward to reproduce through a browser because they
 * depend on how many charts an answer happens to return.
 */

import { describe, expect, it } from "vitest";
import {
  cardShrinkFactor,
  chartScaleFactor,
  MAX_CARD_PAGE_FILL,
  pageBreak,
  type Band,
} from "./download_pdf";

/** A4 content box at scale 2, roughly: 717px wide, 273mm tall. */
const PAGE = 2000;
const CANVAS = 10000;

describe("chartScaleFactor", () => {
  it("shrinks a chart that is wider than the page", () => {
    // The reported crop: a single-column chart drawn at 784px on screen, into
    // a 717px page. Left unscaled, its right edge ran off the page.
    const factor = chartScaleFactor(717, 784);
    expect(factor).toBeLessThan(1);
    expect(784 * factor).toBeCloseTo(717, 5);
  });

  it("grows a chart that is narrower than the page", () => {
    // Two-column layout: the chart occupies about half the card.
    const factor = chartScaleFactor(717, 379);
    expect(717 / 379).toBeGreaterThan(1);
    expect(379 * factor).toBeCloseTo(717, 5);
  });

  it("caps how far a small chart is blown up", () => {
    expect(chartScaleFactor(717, 100)).toBe(2);
  });

  it("never caps shrinking — any overflow is a crop", () => {
    const factor = chartScaleFactor(717, 5000);
    expect(5000 * factor).toBeCloseTo(717, 5);
  });

  it("leaves the chart alone when it already fits exactly", () => {
    expect(chartScaleFactor(717, 717)).toBe(1);
  });

  it("falls back to 1 on a zero measurement rather than dividing by zero", () => {
    expect(chartScaleFactor(0, 400)).toBe(1);
    expect(chartScaleFactor(717, 0)).toBe(1);
  });
});

describe("pageBreak", () => {
  it("uses the full page when nothing is in the way", () => {
    expect(pageBreak(0, PAGE, CANVAS, [])).toBe(PAGE);
  });

  it("returns only the remainder on the last page", () => {
    expect(pageBreak(9500, PAGE, CANVAS, [])).toBe(500);
  });

  it("ends the page early rather than slicing a chart in half", () => {
    // The reported bug: a chart spanning the boundary had its plot on one page
    // and its axis labels and legend on the next, sheared through the middle.
    const chart: Band = { top: 1800, bottom: 2600 };
    expect(pageBreak(0, PAGE, CANVAS, [chart])).toBe(1800);
  });

  it("leaves a chart alone when it does not cross the boundary", () => {
    expect(pageBreak(0, PAGE, CANVAS, [{ top: 200, bottom: 900 }])).toBe(PAGE);
  });

  it("splits a chart that is taller than a page, having nowhere else to put it", () => {
    // Moving the break would not help: it cannot fit on the next page either.
    const tall: Band = { top: 1500, bottom: 4200 };
    expect(pageBreak(0, PAGE, CANVAS, [tall])).toBe(PAGE);
  });

  it("splits rather than emitting a nearly empty page", () => {
    // A chart starting 100px into a 2000px page. Breaking there would leave a
    // page that is 5% full, which reads worse than the split it avoids.
    const early: Band = { top: 100, bottom: 2500 };
    expect(pageBreak(0, PAGE, CANVAS, [early])).toBe(PAGE);
  });

  it("moves the break when the page is filled past the threshold", () => {
    // Same shape, but the chart starts past MIN_PAGE_FILL (25% of 2000).
    const late: Band = { top: 600, bottom: 2500 };
    expect(pageBreak(0, PAGE, CANVAS, [late])).toBe(600);
  });

  it("measures the fill threshold from the page start, not the canvas start", () => {
    // Second page: offset 2000, chart at 2700 is 700px in — past the threshold.
    const band: Band = { top: 2700, bottom: 4500 };
    expect(pageBreak(2000, PAGE, CANVAS, [band])).toBe(700);
  });

  it("picks the band that actually straddles the boundary", () => {
    const bands: Band[] = [
      { top: 100, bottom: 500 },
      { top: 1900, bottom: 2400 },
      { top: 3000, bottom: 3500 },
    ];
    expect(pageBreak(0, PAGE, CANVAS, bands)).toBe(1900);
  });

  it("never returns a non-positive height, which would loop forever", () => {
    // A band starting exactly at the offset would otherwise shorten to zero.
    const band: Band = { top: 2000, bottom: 3000 };
    expect(pageBreak(2000, PAGE, CANVAS, [band])).toBeGreaterThan(0);
  });
});

describe("cardShrinkFactor", () => {
  // A card is chart plus chrome: border, padding, whatever sits beside the
  // chart. Only the chart part can be scaled, so the chrome comes out of the
  // height budget before the factor is worked out.
  const CHROME = 40;

  it("leaves a card that already fits alone", () => {
    expect(cardShrinkFactor(800, 760, 1000)).toBe(1);
  });

  it("shrinks an over-tall card to exactly the cap", () => {
    const factor = cardShrinkFactor(1200, 1200 - CHROME, 900);
    expect(CHROME + (1200 - CHROME) * factor).toBeCloseTo(900, 5);
  });

  it("takes the chrome out of the budget before scaling", () => {
    // Same chart, more chrome — the chart has to shrink further to pay for it.
    const light = cardShrinkFactor(1200, 1200 - 20, 900);
    const heavy = cardShrinkFactor(1200, 1200 - 200, 900);
    expect(heavy).toBeLessThan(light);
  });

  it("gives up when the chrome alone overruns the budget", () => {
    // Nothing a scale factor can do; shrinking the chart towards nothing
    // chasing it would be worse than the split it is avoiding.
    expect(cardShrinkFactor(1200, 100, 80)).toBe(1);
  });

  it("gives up on a card with no measurable chart in it", () => {
    expect(cardShrinkFactor(1200, 0, 900)).toBe(1);
  });
});

describe("the height cap and the page break together", () => {
  // The two halves of the fix only work as a pair: capping the card height is
  // what puts pageBreak's two fall-throughs — a block taller than a page, and
  // a block starting too near the top of one — out of reach for a chart.
  it("never splits a capped card, wherever on the page it lands", () => {
    const height = Math.floor(PAGE * MAX_CARD_PAGE_FILL);
    for (let top = 0; top <= PAGE; top += 7) {
      const card: Band = { top, bottom: top + height };
      const boundary = pageBreak(0, PAGE, CANVAS, [card]);
      const split = card.top < boundary && card.bottom > boundary;
      expect(split, `card at ${top}-${card.bottom} split at ${boundary}`).toBe(false);
    }
  });

  it("splits an uncapped card, which is the bug the cap exists to prevent", () => {
    // The reported defect, as arithmetic. A two-column chart upscaled to fill a
    // single-column page came out at 92% of a page; landing a fifth of the way
    // down, it crossed the boundary, and the break could not be moved without
    // emitting a page a fifth full. So the chart was sliced instead.
    const top = Math.floor(PAGE * 0.2);
    const card: Band = { top, bottom: top + Math.floor(PAGE * 0.92) };
    const boundary = pageBreak(0, PAGE, CANVAS, [card]);
    expect(card.top < boundary && card.bottom > boundary).toBe(true);
    // The cap would have brought that same card back under the boundary.
    expect(top + PAGE * MAX_CARD_PAGE_FILL).toBeLessThanOrEqual(PAGE);
  });
});
