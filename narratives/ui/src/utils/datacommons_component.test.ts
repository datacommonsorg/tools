import { describe, expect, it } from "vitest";
import { dcChartRenderState } from "./datacommons_component";

/**
 * Builds a stand-in for a mounted `<datacommons-*>` element whose open shadow
 * root holds `markup`.
 *
 * The markup in these cases is the shape the upstream bundle renders — a
 * `.chart-container` with a `.chart-headers` strip for the plotted types, a
 * `.ranking-list` for ranking, a `.chart-container.highlight-tile` for
 * highlight — reduced to the nodes the check actually reads.
 */
function dcElement(markup: string | null): Element {
  const host = document.createElement("div");
  if (markup === null) return host; // not upgraded: no shadow root yet
  const root = host.attachShadow({ mode: "open" });
  root.innerHTML = markup;
  return host;
}

const NO_DATA = "No data available.";

describe("dcChartRenderState", () => {
  it("reads a missing element as pending", () => {
    expect(dcChartRenderState(null)).toBe("pending");
  });

  it("reads an element that has not attached its shadow root as pending", () => {
    // Lit attaches the shadow root on first update, so there is a window
    // after appendChild where the element is mounted and empty.
    expect(dcChartRenderState(dcElement(null))).toBe("pending");
  });

  it("reads an attached but still-empty shadow root as pending", () => {
    expect(dcChartRenderState(dcElement(""))).toBe("pending");
  });

  it("reads a loading container as pending, not empty", () => {
    // The error node is not rendered while the fetch is in flight, so its
    // absence is not evidence of data.
    expect(
      dcChartRenderState(
        dcElement('<div class="chart-container loading"></div>'),
      ),
    ).toBe("pending");
  });

  it("reads a settled container with no marks yet as pending", () => {
    expect(
      dcChartRenderState(
        dcElement(
          '<div class="chart-container">' +
            '<div class="chart-headers"></div>' +
            '<div class="svg-container"></div>' +
            "</div>",
        ),
      ),
    ).toBe("pending");
  });

  it("reads the no-data banner on a plotted chart as empty", () => {
    expect(
      dcChartRenderState(
        dcElement(
          '<div class="chart-container">' +
            `<div class="chart-headers"><h4 class="text-danger">${NO_DATA}</h4>` +
            "<h4>Annual Wildfire Burned Area</h4></div>" +
            '<div class="svg-container" style="display: none"></div>' +
            "</div>",
        ),
      ),
    ).toBe("empty");
  });

  it("reads the no-data message on a ranking tile as empty", () => {
    // Ranking renders the same message without the .text-danger class, which
    // is why the check reads text rather than looking for that class.
    expect(
      dcChartRenderState(
        dcElement(
          `<div class="ranking-list"><div class="ranking-header-section">` +
            `<h4>Top states</h4></div><div>${NO_DATA}</div></div>`,
        ),
      ),
    ).toBe("empty");
  });

  it("reads the no-data message on a highlight tile as empty", () => {
    expect(
      dcChartRenderState(
        dcElement(
          '<div class="chart-container highlight-tile">' +
            `<span class="desc">Burned area</span><span>${NO_DATA}</span>` +
            "</div>",
        ),
      ),
    ).toBe("empty");
  });

  it("reads a drawn svg chart as drawn", () => {
    expect(
      dcChartRenderState(
        dcElement(
          '<div class="chart-container">' +
            '<div class="chart-headers"><h4>Burned area</h4></div>' +
            '<div class="svg-container"><svg></svg></div>' +
            "</div>",
        ),
      ),
    ).toBe("drawn");
  });

  it("reads a populated ranking table as drawn", () => {
    expect(
      dcChartRenderState(
        dcElement(
          '<div class="ranking-list"><table><tbody><tr><td>California</td>' +
            "<td>1,000</td></tr></tbody></table></div>",
        ),
      ),
    ).toBe("drawn");
  });

  it("reads a highlight tile showing a number as drawn", () => {
    expect(
      dcChartRenderState(
        dcElement(
          '<div class="chart-container highlight-tile">' +
            '<span class="stat"><span class="number">4.3M</span></span>' +
            "</div>",
        ),
      ),
    ).toBe("drawn");
  });

  it("reads one empty layer of a multi-container component as empty", () => {
    // A component can render more than one container (map layers). One of
    // them having nothing to draw is enough to make the card useless.
    expect(
      dcChartRenderState(
        dcElement(
          '<div class="chart-container"><div class="svg-container">' +
            "<svg></svg></div></div>" +
            '<div class="chart-container"><div class="chart-headers">' +
            `<h4 class="text-danger">${NO_DATA}</h4></div></div>`,
        ),
      ),
    ).toBe("empty");
  });

  it("does not read a per-capita failure as no data", () => {
    // A different errorMsg from the same catalogue. It means the chart could
    // not divide, not that the fetch came back empty, so it is left alone.
    expect(
      dcChartRenderState(
        dcElement(
          '<div class="chart-container"><div class="chart-headers">' +
            '<h4 class="text-danger">Could not calculate per capita.</h4>' +
            '</div><div class="svg-container"><svg></svg></div></div>',
        ),
      ),
    ).toBe("drawn");
  });
});
