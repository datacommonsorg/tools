/**
 * @fileoverview Derives, from one turn's tool calls, which variables and which
 * data sources the answer was actually built on.
 */

import type { ChartConfig, ProvenanceItem, ToolCallEvent } from "../hooks/use_sse_chat";

/** Tools that fetch numbers, and so are the ones that pin a source. */
const OBSERVATION_TOOLS = new Set([
  "get_observations",
  "get_child_observations",
  "get_multi_entity_observations",
]);

/** A statistical variable the turn touched. */
export interface VariableUse {
  dcid: string;
  /** Human-readable name, when a search or metadata call revealed one. */
  name?: string;
  /** Tools that referenced it, in call order. */
  referencedBy: string[];
  /** True when an observation call actually fetched numbers for it. */
  fetched: boolean;
}

/** How a facet came to supply the numbers, if it did. */
export type FacetUse =
  /** Offered by a metadata call but never returned any data. */
  | "unused"
  /** The agent pinned it with source_override. */
  | "chosen"
  /** The server returned it because the agent pinned nothing. */
  | "server-default";

/**
 * One source ("facet") for a variable. get_variable_metadata reports every
 * candidate; the observation results say which one actually supplied the
 * numbers, whether or not the agent asked for it by name.
 */
export interface FacetInfo {
  facetId: string;
  /** Dataset name, e.g. "World Development Indicators". */
  provenance?: string;
  /** Licence terms, when reported. */
  license?: string;
  url?: string;
  /** Number of observations available. */
  obsCount?: number;
  /** Coverage, e.g. "1960–2024". */
  dateRange?: string;
  unit?: string;
  /** Which variable(s) this facet was offered for. */
  forVariables: string[];
  /** True when this facet supplied data, however it was selected. */
  used: boolean;
  /** Whether the agent pinned it, or the server fell back to it. */
  use: FacetUse;
}

export interface TurnInspection {
  variables: VariableUse[];
  /** Place DCIDs referenced by observation calls, deduplicated. */
  places: string[];
  /** Every facet the metadata calls revealed, used ones first. */
  facets: FacetInfo[];
  /**
   * True when at least one observation call pinned a source with
   * source_override. When false the server chose for the agent, which is worth
   * knowing: two sources for the same variable and year can disagree
   * substantially, and nobody reviewed which one answered.
   */
  sourceChosenExplicitly: boolean;
  /** Chart variable/place pairs the agent asked the UI to render. */
  charts: { title: string; variables: string[]; places: string[] }[];
}

/** Parses a tool result, tolerating anything that is not the JSON we expect. */
function parseResult(result: string | undefined): Record<string, unknown> | null {
  if (!result) return null;
  try {
    const parsed = JSON.parse(result);
    return parsed && typeof parsed === "object" ? (parsed as Record<string, unknown>) : null;
  } catch {
    // Error strings and truncated payloads land here. Not exceptional.
    return null;
  }
}

/** Reads a string-keyed record off an unknown value, or null. */
function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function asString(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value.trim() : undefined;
}

/** Collects the DCIDs an argument names, whether it is a string or a list. */
function dcidsFrom(value: unknown): string[] {
  if (typeof value === "string") return [value];
  if (Array.isArray(value)) return value.filter((v): v is string => typeof v === "string");
  // get_multi_entity_observations takes a role -> DCID[] map.
  const record = asRecord(value);
  if (record) return Object.values(record).flatMap(dcidsFrom);
  return [];
}

/**
 * Builds the facet table from get_variable_metadata results.
 *
 * That tool is the only one that reports a facet's dataset name, licence, date
 * range and observation count; the observation tools return just an id. Joining
 * them is what turns "source_override: 16633743049422531122" into "NITI India
 * Population Projection, 2011–2026, 16 observations".
 */
function collectFacets(calls: ToolCallEvent[]): Map<string, FacetInfo> {
  const facets = new Map<string, FacetInfo>();

  for (const call of calls) {
    if (call.name !== "get_variable_metadata") continue;
    const payload = parseResult(call.result);
    if (!payload) continue;

    const provenances = asRecord(payload.provenances) ?? {};
    const variables = asRecord(payload.variables) ?? {};

    for (const [variableDcid, rawVariable] of Object.entries(variables)) {
      const variable = asRecord(rawVariable);
      const list = Array.isArray(variable?.facets) ? variable!.facets : [];
      for (const rawFacet of list) {
        const facet = asRecord(rawFacet);
        const facetId = asString(facet?.id);
        if (!facet || !facetId) continue;

        const provenance = asRecord(provenances[String(facet.provenanceId)]);
        const props = asRecord(provenance?.properties) ?? {};
        const facetProps = asRecord(facet.properties) ?? {};
        const range = asRecord(facet.dateRange);
        const start = asString(range?.start);
        const end = asString(range?.end);

        const existing = facets.get(facetId);
        if (existing) {
          if (!existing.forVariables.includes(variableDcid)) {
            existing.forVariables.push(variableDcid);
          }
          continue;
        }

        facets.set(facetId, {
          facetId,
          // isPartOf is the dataset; source is the publisher. The dataset is
          // the provenance a reader needs.
          provenance: asString(props.isPartOf) ?? asString(props.source),
          license: asString(props.licenseType),
          url: asString(props.url) ?? asString(props.descriptionUrl),
          obsCount: typeof facet.obsCount === "number" ? facet.obsCount : undefined,
          dateRange: start && end ? (start === end ? start : `${start}–${end}`) : start ?? end,
          unit: asString(facetProps.unit),
          forVariables: [variableDcid],
          used: false,
          use: "unused",
        });
      }
    }
  }

  return facets;
}

/** Reads variable DCID -> display name out of search and metadata results. */
function collectNames(calls: ToolCallEvent[]): Map<string, string> {
  const names = new Map<string, string>();
  for (const call of calls) {
    const payload = parseResult(call.result);
    if (!payload) continue;

    // Search results carry a flat mapping, in either spelling.
    for (const key of ["dcidNameMappings", "dcid_name_mappings"]) {
      const mapping = asRecord(payload[key]);
      if (!mapping) continue;
      for (const [dcid, name] of Object.entries(mapping)) {
        const label = asString(name);
        if (label && !names.has(dcid)) names.set(dcid, label);
      }
    }

    // Metadata and observation results name the variable directly.
    const variables = asRecord(payload.variables);
    if (variables) {
      for (const [dcid, raw] of Object.entries(variables)) {
        const label = asString(asRecord(raw)?.name);
        if (label && !names.has(dcid)) names.set(dcid, label);
      }
    }
    const single = asRecord(payload.variable);
    const singleDcid = asString(single?.dcid);
    const singleName = asString(single?.name);
    if (singleDcid && singleName && !names.has(singleDcid)) {
      names.set(singleDcid, singleName);
    }
  }
  return names;
}

/**
 * The facet an observation result was actually served from.
 *
 * The server reports this whether or not the agent asked for it by name, and
 * the id is the same one get_variable_metadata lists as a facet. That identity
 * is what lets a server-chosen source be named rather than left as "nobody
 * chose" -- without it, a turn that pinned nothing shows every candidate as
 * unused, which reads as though none of them supplied the numbers.
 *
 * snake_case is accepted too: server 1.2.1 spelled it `source_metadata` /
 * `source_id`.
 */
function servedFacetId(payload: Record<string, unknown> | null): string | undefined {
  if (!payload) return undefined;
  const metadata =
    asRecord(payload.sourceMetadata) ?? asRecord(payload.source_metadata);
  if (!metadata) return undefined;
  const id = asString(metadata.sourceId) ?? asString(metadata.source_id);
  // 1.2.1 used the literal "unknown" for an empty result rather than omitting it.
  return id && id !== "unknown" ? id : undefined;
}

/**
 * Summarises what a turn actually used.
 *
 * Everything is derived from data already in the browser -- the tool calls the
 * agent streamed -- so this adds no request and cannot disagree with what the
 * answer was built from.
 */
export function inspectTurn(
  toolCalls: ToolCallEvent[],
  chartConfig?: ChartConfig,
  _provenance?: ProvenanceItem[],
): TurnInspection {
  const calls = toolCalls ?? [];
  const facets = collectFacets(calls);
  const names = collectNames(calls);

  const variables = new Map<string, VariableUse>();
  const places = new Set<string>();
  let sourceChosenExplicitly = false;

  const noteVariable = (dcid: string, tool: string, fetched: boolean) => {
    const entry = variables.get(dcid);
    if (entry) {
      if (!entry.referencedBy.includes(tool)) entry.referencedBy.push(tool);
      entry.fetched = entry.fetched || fetched;
      return;
    }
    variables.set(dcid, {
      dcid,
      name: names.get(dcid),
      referencedBy: [tool],
      fetched,
    });
  };

  for (const call of calls) {
    const args = call.arguments ?? {};
    const isObservation = OBSERVATION_TOOLS.has(call.name);

    for (const key of ["variable_dcid", "variable_dcids"]) {
      for (const dcid of dcidsFrom(args[key])) noteVariable(dcid, call.name, isObservation);
    }

    if (isObservation) {
      for (const key of ["place_dcid", "parent_place_dcid", "entity_dcids", "entities"]) {
        for (const dcid of dcidsFrom(args[key])) places.add(dcid);
      }
      const override = asString(args.source_override);
      if (override) sourceChosenExplicitly = true;

      // Prefer what the server says it served over what was asked for: if the
      // two ever disagree, the served id is the one the numbers came from.
      const served = servedFacetId(parseResult(call.result)) ?? override;
      if (served) {
        const use: FacetUse = override ? "chosen" : "server-default";
        const known = facets.get(served);
        if (known) {
          known.used = true;
          // "chosen" wins: one deliberate pick outranks a later fallback.
          if (known.use !== "chosen") known.use = use;
        } else {
          // No metadata call described this facet, so it has an id and nothing
          // else. Still worth showing -- it is where the numbers came from.
          facets.set(served, { facetId: served, forVariables: [], used: true, use });
        }
      }
    }
  }

  const charts = (chartConfig?.charts ?? []).map((chart) => ({
    title: chart.title ?? "(untitled)",
    variables: chart.variableDcids ?? [],
    places: chart.placeDcids ?? [],
  }));

  return {
    variables: [...variables.values()],
    places: [...places],
    // Used facets first: those are what the answer rests on.
    facets: [...facets.values()].sort((a, b) => Number(b.used) - Number(a.used)),
    sourceChosenExplicitly,
    charts,
  };
}
