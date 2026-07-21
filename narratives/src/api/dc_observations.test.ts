/**
 * @fileoverview Tests for the dc_observations pivot/formatting helpers.
 */

import { describe, it, expect, vi, afterEach } from "vitest";
import {
  fetchSeries,
  fetchPoint,
  pivotSeriesToRows,
  pivotPointToRowsByPlace,
  pickSourceFromFacets,
  getPrettyPlaceName,
  getPrettyVariableName,
  type SeriesResponse,
  type PointResponse,
} from "./dc_observations";

describe("fetchSeries / fetchPoint", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("fetchSeries resolves the parsed JSON on a 200", async () => {
    const payload: SeriesResponse = { data: {}, facets: {} };
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify(payload), { status: 200 })),
    );
    await expect(fetchSeries(["Count_Person"], ["country/IND"])).resolves.toEqual(
      payload,
    );
  });

  it("fetchSeries throws on a non-ok response", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("", { status: 500 })));
    await expect(fetchSeries(["v"], ["p"])).rejects.toThrow(/HTTP 500/);
  });

  it("fetchPoint throws on a non-ok response", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("", { status: 404 })));
    await expect(fetchPoint(["v"], ["p"], "2021")).rejects.toThrow(/HTTP 404/);
  });
});

describe("pivotSeriesToRows", () => {
  const response: SeriesResponse = {
    data: {
      var_a: {
        "country/IND": {
          series: [
            { date: "2020", value: 10 },
            { date: "2021", value: 20 },
          ],
        },
      },
      var_b: {
        "country/IND": {
          series: [{ date: "2021", value: 7 }],
        },
      },
    },
    facets: {},
  };

  it("merges variables into one row per date, keyed by variable dcid", () => {
    const rows = pivotSeriesToRows(response, ["var_a", "var_b"], "country/IND");
    expect(rows).toEqual([
      { date: "2020", var_a: 10 },
      { date: "2021", var_a: 20, var_b: 7 },
    ]);
  });

  it("omits variables with no value on a given date", () => {
    const rows = pivotSeriesToRows(response, ["var_a", "var_b"], "country/IND");
    expect(rows[0]).not.toHaveProperty("var_b");
  });

  it("sorts rows by date ascending", () => {
    const rows = pivotSeriesToRows(response, ["var_a"], "country/IND");
    expect(rows.map((row) => row.date)).toEqual(["2020", "2021"]);
  });

  it("returns an empty array when the place has no data", () => {
    expect(pivotSeriesToRows(response, ["var_a"], "country/USA")).toEqual([]);
  });

  it("tolerates a missing data section", () => {
    const empty = { data: {}, facets: {} } as SeriesResponse;
    expect(pivotSeriesToRows(empty, ["var_a"], "country/IND")).toEqual([]);
  });
});

describe("pivotPointToRowsByPlace", () => {
  const response: PointResponse = {
    data: {
      var_a: {
        "country/IND": { date: "2021", value: 42 },
        "country/USA": { date: "2021", value: 100 },
        "country/NPL": { date: "2021" },
      },
    },
    facets: {},
  };

  it("returns one row per place with a numeric value", () => {
    expect(pivotPointToRowsByPlace(response, "var_a")).toEqual([
      { place: "country/IND", value: 42 },
      { place: "country/USA", value: 100 },
    ]);
  });

  it("drops places without a numeric value", () => {
    const places = pivotPointToRowsByPlace(response, "var_a").map(
      (row) => row.place,
    );
    expect(places).not.toContain("country/NPL");
  });

  it("returns an empty array for an unknown variable", () => {
    expect(pivotPointToRowsByPlace(response, "var_missing")).toEqual([]);
  });
});

describe("pickSourceFromFacets", () => {
  it("returns the first facet that has a provenanceUrl", () => {
    const response = {
      data: {},
      facets: {
        f1: { unit: "Years" },
        f2: { importName: "WHO", provenanceUrl: "https://who.int" },
      },
    } as SeriesResponse;
    expect(pickSourceFromFacets(response)).toEqual({
      name: "WHO",
      url: "https://who.int",
    });
  });

  it("falls back to the url as the name when importName is absent", () => {
    const response = {
      data: {},
      facets: { f1: { provenanceUrl: "https://example.org" } },
    } as SeriesResponse;
    expect(pickSourceFromFacets(response)).toEqual({
      name: "https://example.org",
      url: "https://example.org",
    });
  });

  it("returns undefined when no facet has a provenanceUrl", () => {
    const response = { data: {}, facets: { f1: { unit: "x" } } } as SeriesResponse;
    expect(pickSourceFromFacets(response)).toBeUndefined();
  });
});

describe("getPrettyPlaceName", () => {
  it("strips a namespace prefix", () => {
    expect(getPrettyPlaceName("country/IND")).toBe("IND");
    expect(getPrettyPlaceName("geoId/06")).toBe("06");
  });

  it("returns the dcid unchanged when there is no prefix", () => {
    expect(getPrettyPlaceName("Earth")).toBe("Earth");
  });
});

describe("getPrettyVariableName", () => {
  it("replaces underscores and slashes with spaces and title-cases", () => {
    expect(getPrettyVariableName("Count_Person")).toBe("Count Person");
    expect(getPrettyVariableName("dc/abc123")).toBe("Dc abc123");
  });

  it("returns an empty string for empty input", () => {
    expect(getPrettyVariableName("")).toBe("");
  });
});
