import { marked } from 'marked';
import { resolvePlaceName } from '~/functions/format_card_title';
import { formatFacetBlock } from '~/functions/format_facet';
import { getResultScopeKey } from '~/functions/scope_key';
import type { ComparisonResult, QueryResult } from '~/server/types';

/**
 * Build a set of variable DCIDs that have time-series data in the result.
 */
const getVariablesWithData = (result: QueryResult): Set<string> => {
  return new Set(
    result.timeSeries
      .filter((ts) => ts.facets.length > 0)
      .map((ts) => ts.variableDcid),
  );
};

/**
 * Strip `#fetch=` markdown links for variables that have no data, converting
 * them to plain text. Links whose `fetch` param is NOT in `withData` become
 * just their display text.
 */
const stripNoDataLinks = (md: string, withData: Set<string>): string => {
  return md.replace(
    /\[([^\]]+)\]\(#fetch=([^&)]+)[^)]*\)/g,
    (match, label: string, dcid: string) => {
      return withData.has(dcid) ? match : label;
    },
  );
};

/** Build the variables table as an HTML string from a query result. */
const buildTableHtml = (result: QueryResult): string => {
  const defaultScopeKey = getResultScopeKey(result);
  const defaultPlaceName = resolvePlaceName(result);
  const intro = result.introduction ?? '';
  const withData = getVariablesWithData(result);

  let md = intro ? `${stripNoDataLinks(intro, withData)}\n\n` : '';
  md += '| Statistical variable | Facet(s) | Rationale |\n';
  md += '| --- | --- | --- |\n';

  for (const variable of result.variables) {
    const timeSeries = result.timeSeries.find(
      (m) => m.variableDcid === variable.dcid,
    );
    const facets = timeSeries?.facets || [];
    const facetCell =
      facets.length > 0
        ? facets.map(formatFacetBlock).join('<br><br>').replace(/\|/g, '\\|')
        : 'No data';

    const scopeKey = variable.isChildQuery
      ? variable.parentPlaceDcid || variable.placeDcid
        ? `${variable.parentPlaceDcid || variable.placeDcid}:${variable.childPlaceType || 'Country'}`
        : defaultScopeKey
      : variable.placeDcid || defaultScopeKey;
    const placeName = variable.placeName || defaultPlaceName;

    const hasData = withData.has(variable.dcid);
    const encodedVar = encodeURIComponent(variable.name);
    const encodedPlace = encodeURIComponent(placeName);
    const nameCell = hasData
      ? `[${variable.name}](#fetch=${variable.dcid}&place=${scopeKey}&varName=${encodedVar}&placeName=${encodedPlace})`
      : variable.name;

    const rationaleCell = variable.rationale
      ? variable.rationale.replace(/\|/g, '\\|')
      : '—';

    md += `| ${nameCell} | ${facetCell} | ${rationaleCell} |\n`;
  }

  return marked.parse(md) as string;
};

/** Build the notes card HTML from a query result's introduction + insights. */
const buildNotesHtml = (result: QueryResult): string => {
  const withData = getVariablesWithData(result);

  let md = '';

  // Insights come first at the top of the card (without bullet points or bold headers)
  if (result.insights && result.insights.length > 0) {
    for (const insight of result.insights) {
      const text = stripNoDataLinks(insight.text, withData);
      md += `${text}\n\n`;
    }
  }

  // "Notes" section follows below
  if (result.coverage || result.introduction) {
    md += '### Notes\n\n';
    if (result.coverage) {
      md += `${stripNoDataLinks(result.coverage, withData)}\n\n`;
    }
    if (result.introduction) {
      md += `${stripNoDataLinks(result.introduction, withData)}\n\n`;
    }
  }

  return marked.parse(md) as string;
};

/** Render pre-built HTML for table and notes cards from a QueryResult. */
export const renderResultHtml = (
  result: QueryResult,
): {
  tableHtml: string;
  notesHtml: string;
} => {
  return {
    tableHtml: buildTableHtml(result),
    notesHtml: buildNotesHtml(result),
  };
};

/** Render comparison notes HTML from a ComparisonResult. */
export const renderComparisonHtml = (comparison: ComparisonResult): string => {
  let md = '';

  // 1. Comparative insights come FIRST (at the top of the card, without header or bullet points)
  if (comparison.insights && comparison.insights.length > 0) {
    for (const insight of comparison.insights) {
      md += `${insight.text}\n\n`;
    }
  }

  // 2. "Notes" section follows below
  if (comparison.coverage || comparison.introduction) {
    md += '### Notes\n\n';
    if (comparison.coverage) {
      md += `${comparison.coverage}\n\n`;
    }
    if (comparison.introduction) {
      md += `${comparison.introduction}\n\n`;
    }
  }

  return marked.parse(md) as string;
};
