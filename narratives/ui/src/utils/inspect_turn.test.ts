/**
 * @fileoverview Tests for inspectTurn.
 *
 * Payload shapes are copied from real responses of MCP server 1.3.0 at
 * api.datacommons.org, so a server-side shape change shows up here as a failure
 * rather than as an empty panel in the UI.
 */

import { describe, expect, it } from "vitest";
import { inspectTurn } from "./inspect_turn";
import type { ToolCallEvent } from "../hooks/use_sse_chat";

const METADATA_RESULT = JSON.stringify({
  status: "SUCCESS",
  variables: {
    Count_Person: {
      id: "Count_Person",
      name: "Total population",
      facets: [
        {
          id: "16450972571663981028",
          provenanceId: "dc/base/IndiaCensus",
          obsCount: 1,
          dateRange: { start: "2011", end: "2011" },
          properties: {},
        },
        {
          id: "16633743049422531122",
          provenanceId: "dc/base/NITI",
          obsCount: 16,
          dateRange: { start: "2011", end: "2026" },
          properties: { unit: "Person" },
        },
      ],
    },
  },
  provenances: {
    "dc/base/IndiaCensus": {
      properties: {
        isPartOf: "India Census Tables",
        source: "Census of India",
        url: "https://censusindia.gov.in/",
        licenseType: "PublicDomain",
      },
    },
    "dc/base/NITI": {
      properties: {
        isPartOf: "NITI India Population Projection",
        url: "https://ndap.niti.gov.in/dataset/7208",
        licenseType: "PublicDomain",
      },
    },
  },
});

const SEARCH_RESULT = JSON.stringify({
  status: "SUCCESS",
  dcidNameMappings: { Count_Person: "Total population", "country/IND": "India" },
  variables: [{ dcid: "Count_Person", placesWithData: ["country/IND"] }],
});

/**
 * A real get_observations envelope, rows trimmed. Captured from
 * api.datacommons.org for Count_Person / country/IND with NO source_override:
 * the server picked NITI on its own, and reported which one it picked.
 */
const OBSERVATION_RESULT = JSON.stringify({
  variable: { dcid: "Count_Person", name: "Total population" },
  sourceMetadata: {
    sourceId: "16633743049422531122",
    measurementMethod: "NITIIndiaProjection",
    provenanceUrl: "https://ndap.niti.gov.in/dataset/7208",
  },
  alternativeSources: [
    { sourceMetadata: { sourceId: "16450972571663981028" } },
  ],
  data: { columns: ["date", "value"], rows: [["2011", 1210854977]] },
});

/**
 * The table summary a fetch function returns, in the shape of the agent's
 * `serialize_fetch_result`: the rows stay on the server, and the places are
 * listed as `name (dcid)` labels.
 */
const FETCH_SUMMARY = JSON.stringify({
  table_id: "t1",
  variable_dcid: "Count_Person",
  variable_name: "Total population",
  observation_count: 128,
  places_with_data_count: 2,
  places_with_data: ["India (country/IND)", "China (country/CHN)"],
  places_without_data_count: 0,
  places_without_data: [],
  date_range: ["1960", "2023"],
  source: { name: "NITI India Population Projection", url: "https://ndap.niti.gov.in/dataset/7208" },
  facet_id: "16633743049422531122",
  unit: "Person",
  scaling_factor: null,
  measurement_method: "NITIIndiaProjection",
  observation_period: "P1Y",
  alternative_sources: [{ source_id: "16450972571663981028" }],
  value_range: [445954579, 1428627663],
  sample_rows: [
    { place_dcid: "country/IND", place_name: "India", date: "2023", value: 1428627663, facet_id: "16633743049422531122" },
  ],
});

const calls = (...items: ToolCallEvent[]) => items;

describe("inspectTurn", () => {
  it("joins a chosen source_override to its dataset name, license and coverage", () => {
    const out = inspectTurn(
      calls(
        { name: "search_indicators", arguments: { query: "population" }, result: SEARCH_RESULT },
        {
          name: "get_variable_metadata",
          arguments: { variable_dcids: ["Count_Person"], entity_dcids: ["country/IND"] },
          result: METADATA_RESULT,
        },
        {
          name: "get_child_observations",
          arguments: {
            variable_dcid: "Count_Person",
            parent_place_dcid: "country/IND",
            child_place_type: "State",
            source_override: "16633743049422531122",
          },
          result: "{}",
        },
      ),
    );

    expect(out.sourceChosenExplicitly).toBe(true);

    // Used facet sorts first, so the answer's actual source leads.
    const used = out.facets[0];
    expect(used.used).toBe(true);
    expect(used.use).toBe("chosen");
    expect(used.facetId).toBe("16633743049422531122");
    expect(used.provenance).toBe("NITI India Population Projection");
    expect(used.license).toBe("PublicDomain");
    expect(used.obsCount).toBe(16);
    expect(used.dateRange).toBe("2011–2026");
    expect(used.unit).toBe("Person");

    // The rejected candidate is still listed, so a reviewer can see the choice.
    const unused = out.facets.find((f) => f.facetId === "16450972571663981028");
    expect(unused?.used).toBe(false);
    expect(unused?.use).toBe("unused");
    expect(unused?.provenance).toBe("India Census Tables");
  });

  it("prefers the dataset (isPartOf) over the publisher (source)", () => {
    const out = inspectTurn(
      calls({ name: "get_variable_metadata", arguments: {}, result: METADATA_RESULT }),
    );
    const census = out.facets.find((f) => f.facetId === "16450972571663981028");
    expect(census?.provenance).toBe("India Census Tables");
    expect(census?.provenance).not.toBe("Census of India");
  });

  it("collapses a single-year range instead of repeating it", () => {
    const out = inspectTurn(
      calls({ name: "get_variable_metadata", arguments: {}, result: METADATA_RESULT }),
    );
    expect(out.facets.find((f) => f.facetId === "16450972571663981028")?.dateRange).toBe("2011");
  });

  it("names the source the server picked when the agent pinned none", () => {
    const out = inspectTurn(
      calls(
        { name: "get_variable_metadata", arguments: {}, result: METADATA_RESULT },
        {
          name: "get_observations",
          arguments: { variable_dcid: "Count_Person", place_dcid: "country/IND" },
          result: OBSERVATION_RESULT,
        },
      ),
    );

    // Nobody chose -- but the numbers still came from somewhere, and the panel
    // has to say where. Before this, every candidate read as unused.
    expect(out.sourceChosenExplicitly).toBe(false);
    const served = out.facets.find((f) => f.facetId === "16633743049422531122");
    expect(served?.used).toBe(true);
    expect(served?.use).toBe("server-default");
    expect(served?.provenance).toBe("NITI India Population Projection");

    const other = out.facets.find((f) => f.facetId === "16450972571663981028");
    expect(other?.use).toBe("unused");
  });

  it("shows a server-picked source that no metadata call described", () => {
    const out = inspectTurn(
      calls({
        name: "get_observations",
        arguments: { variable_dcid: "Count_Person", place_dcid: "country/IND" },
        result: OBSERVATION_RESULT,
      }),
    );
    expect(out.facets).toHaveLength(1);
    expect(out.facets[0].facetId).toBe("16633743049422531122");
    expect(out.facets[0].use).toBe("server-default");
    // No metadata call, so there is an id and nothing else to show with it.
    expect(out.facets[0].provenance).toBeUndefined();
  });

  it("does not downgrade a chosen source when a later call falls back to it", () => {
    const out = inspectTurn(
      calls(
        { name: "get_variable_metadata", arguments: {}, result: METADATA_RESULT },
        {
          name: "get_observations",
          arguments: {
            variable_dcid: "Count_Person",
            place_dcid: "country/IND",
            source_override: "16633743049422531122",
          },
          result: OBSERVATION_RESULT,
        },
        // Same facet, this time unpinned. One deliberate pick outranks it.
        {
          name: "get_observations",
          arguments: { variable_dcid: "Count_Person", place_dcid: "country/CHN" },
          result: OBSERVATION_RESULT,
        },
      ),
    );
    expect(out.facets[0].use).toBe("chosen");
  });

  it("reads the 1.2.1 snake_case spelling of the served source", () => {
    const out = inspectTurn(
      calls({
        name: "get_observations",
        arguments: { variable_dcid: "Count_Person", place_dcid: "country/IND" },
        result: JSON.stringify({ source_metadata: { source_id: "12345" } }),
      }),
    );
    expect(out.facets[0]?.facetId).toBe("12345");
    expect(out.facets[0]?.use).toBe("server-default");
  });

  it("ignores the literal \"unknown\" source id an empty result carries", () => {
    const out = inspectTurn(
      calls({
        name: "get_observations",
        arguments: { variable_dcid: "Count_Person", place_dcid: "country/IND" },
        result: JSON.stringify({ sourceMetadata: { sourceId: "unknown" }, data: {} }),
      }),
    );
    expect(out.facets).toHaveLength(0);
  });

  it("flags when no source was chosen, so the server picked", () => {
    const out = inspectTurn(
      calls({
        name: "get_observations",
        arguments: { variable_dcid: "Count_Person", place_dcid: "country/IND" },
        result: "{}",
      }),
    );
    expect(out.sourceChosenExplicitly).toBe(false);
  });

  it("names variables from a search result and marks which were fetched", () => {
    const out = inspectTurn(
      calls(
        { name: "search_indicators", arguments: { query: "population" }, result: SEARCH_RESULT },
        {
          name: "get_observations",
          arguments: { variable_dcid: "Count_Person", place_dcid: "country/IND" },
          result: "{}",
        },
      ),
    );
    const variable = out.variables.find((v) => v.dcid === "Count_Person");
    expect(variable?.name).toBe("Total population");
    expect(variable?.fetched).toBe(true);
    // Only calls that actually name the DCID count. search_indicators takes a
    // free-text query, so it supplies the display name but is not a reference.
    expect(variable?.referencedBy).toEqual(["get_observations"]);
    expect(out.places).toEqual(["country/IND"]);
  });

  it("does not mark a variable fetched when only searched", () => {
    const out = inspectTurn(
      calls({ name: "search_indicators", arguments: { query: "x" }, result: SEARCH_RESULT }),
    );
    // Search results name variables but the loop only records ones passed as
    // arguments, so nothing is fetched and nothing is invented.
    expect(out.variables.every((v) => !v.fetched)).toBe(true);
  });

  it("flattens the multi-entity role map into places", () => {
    const out = inspectTurn(
      calls({
        name: "get_multi_entity_observations",
        arguments: {
          variable_dcid: "Amount_ODA",
          entities: { donor: ["country/DEU"], recipient: ["country/KEN"] },
        },
        result: "{}",
      }),
    );
    expect(out.places.sort()).toEqual(["country/DEU", "country/KEN"]);
  });

  it("lists the parent place of a multi-entity cohort expansion", () => {
    // Test: Places of a multi-entity fetch that expands a role into children.
    // Situation: A `fetch_multi_entity_observations` call expands the
    //   `recipient` role into the countries of `Earth`, and its compact
    //   summary carries no table and no `places_with_data`.
    // Expectation: The fixed donor and the parent of the expansion are
    //   listed.
    const out = inspectTurn(
      calls({
        name: "fetch_multi_entity_observations",
        arguments: {
          variable_dcid: "Amount_ODA",
          entities: { donor: ["country/DEU"] },
          parent_entity_property: "recipient",
          parent_entity_dcid: "Earth",
          child_entity_type: "Country",
        },
        result: JSON.stringify({ table_id: null, row_count: 0 }),
      }),
    );
    expect(out.places.sort()).toEqual(["Earth", "country/DEU"]);
  });

  it("reads the served facet, the name, and the places from a fetch summary", () => {
    // Test: Inspection of the server-side fetch functions.
    // Situation: A `fetch_observations` call names two places and returns
    //   the table summary the agent streams, which carries `facet_id`,
    //   `variable_name`, and `places_with_data`; a metadata call described
    //   the facet earlier.
    // Expectation: The variable is marked fetched under its summary name,
    //   both places are listed, and the facet is marked used as the
    //   server's default with its metadata joined.
    const out = inspectTurn(
      calls(
        { name: "get_variable_metadata", arguments: {}, result: METADATA_RESULT },
        {
          name: "fetch_observations",
          arguments: { variable_dcid: "Count_Person", place_dcids: ["country/IND", "country/CHN"] },
          result: FETCH_SUMMARY,
        },
      ),
    );

    const variable = out.variables.find((v) => v.dcid === "Count_Person");
    expect(variable?.fetched).toBe(true);
    expect(variable?.name).toBe("Total population");
    expect(variable?.referencedBy).toEqual(["fetch_observations"]);
    expect(out.places.sort()).toEqual(["country/CHN", "country/IND"]);
    expect(out.sourceChosenExplicitly).toBe(false);
    const served = out.facets.find((f) => f.facetId === "16633743049422531122");
    expect(served?.used).toBe(true);
    expect(served?.use).toBe("server-default");
    expect(served?.provenance).toBe("NITI India Population Projection");
  });

  it("lists the places a cohort fetch returned and the cohort's parent", () => {
    // Test: Places of fetches that name none in their arguments.
    // Situation: Two `fetch_child_observations` calls name only a parent
    //   place, so only their summaries say which places they fetched, and
    //   the second pins a facet.
    // Expectation: The parent and the places from both summaries are all
    //   listed once, and the pinned facet is marked as chosen.
    const out = inspectTurn(
      calls(
        {
          name: "fetch_child_observations",
          arguments: {
            variable_dcid: "Count_Person",
            parent_place_dcid: "country/IND",
            child_place_type: "State",
          },
          result: FETCH_SUMMARY,
        },
        {
          name: "fetch_child_observations",
          arguments: {
            variable_dcid: "Median_Income",
            parent_place_dcid: "country/IND",
            child_place_type: "State",
            source_override: "999",
          },
          result: JSON.stringify({
            table_id: "t2",
            variable_dcid: "Median_Income",
            places_with_data: ["wikidataId/Q1159", "wikidataId/Q1445"],
            facet_id: "999",
          }),
        },
      ),
    );

    expect(out.places).toEqual([
      "country/IND",
      "country/CHN",
      "wikidataId/Q1159",
      "wikidataId/Q1445",
    ]);
    expect(out.sourceChosenExplicitly).toBe(true);
    expect(out.facets.find((f) => f.facetId === "999")?.use).toBe("chosen");
  });

  it("shows a source_override that no metadata call described", () => {
    const out = inspectTurn(
      calls({
        name: "get_observations",
        arguments: { variable_dcid: "V", place_dcid: "P", source_override: "999" },
        result: "{}",
      }),
    );
    const facet = out.facets.find((f) => f.facetId === "999");
    expect(facet?.used).toBe(true);
    expect(facet?.provenance).toBeUndefined();
  });

  it("survives an error string or malformed result", () => {
    expect(() =>
      inspectTurn(
        calls(
          { name: "get_observations", arguments: { variable_dcid: "V" }, result: "Unknown tool: x" },
          { name: "get_variable_metadata", arguments: {}, result: undefined },
          { name: "search_indicators", arguments: {}, result: "[1,2,3]" },
        ),
      ),
    ).not.toThrow();
  });

  it("handles no tool calls at all", () => {
    const out = inspectTurn([]);
    expect(out.variables).toEqual([]);
    expect(out.facets).toEqual([]);
    expect(out.sourceChosenExplicitly).toBe(false);
  });

  it("maps the chart config the agent asked to render", () => {
    const out = inspectTurn([], {
      shouldRender: true,
      charts: [
        {
          vizType: "bar",
          title: "Population across states",
          variableDcids: ["Count_Person"],
          placeDcids: ["wikidataId/Q1498"],
        },
      ],
    });
    expect(out.charts).toEqual([
      { title: "Population across states", variables: ["Count_Person"], places: ["wikidataId/Q1498"] },
    ]);
  });
});
