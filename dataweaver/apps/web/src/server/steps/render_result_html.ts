import { marked } from 'marked';
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
  const entityDcid = result.entities[0]?.dcid ?? '';
  const placeName = result.entities[0]?.name ?? '';
  const intro = result.introduction ?? '';
  const withData = getVariablesWithData(result);

  let md = intro ? `${stripNoDataLinks(intro, withData)}\n\n` : '';
  md += '| Statistical variable | Facet(s) | Rationale |\n';
  md += '| --- | --- | --- |\n';

  for (const variable of result.variables) {
    const timeSeries = result.timeSeries.find(
      (m) => m.variableDcid === variable.dcid,
    );
    const firstFacet = timeSeries?.facets[0];
    const facetCell = firstFacet
      ? `${firstFacet.source}<br>${firstFacet.earliestDate} – ${firstFacet.latestDate}${firstFacet.unit ? ` · ${firstFacet.unit}` : ''}`
      : 'No data';

    const hasData = withData.has(variable.dcid);
    const encodedVar = encodeURIComponent(variable.name);
    const encodedPlace = encodeURIComponent(placeName);
    const nameCell = hasData
      ? `[${variable.name}](#fetch=${variable.dcid}&place=${entityDcid}&varName=${encodedVar}&placeName=${encodedPlace})`
      : variable.name;

    md += `| ${nameCell} | ${facetCell} | ${variable.rationale ?? '—'} |\n`;
  }

  return marked.parse(md) as string;
};

/** Build the notes card HTML from a query result's introduction + insights. */
const buildNotesHtml = (result: QueryResult): string => {
  const withData = getVariablesWithData(result);

  let md = '### About this data\n\n';
  if (result.coverage) {
    md += `${stripNoDataLinks(result.coverage, withData)}\n\n`;
  }
  if (result.introduction) {
    md += `${stripNoDataLinks(result.introduction, withData)}\n\n`;
  }

  if (result.insights && result.insights.length > 0) {
    md += '### Relevant insights\n\n';
    for (const insight of result.insights) {
      md += `- **${insight.title}**: ${stripNoDataLinks(insight.text, withData)}\n`;
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

  if (comparison.coverage) {
    md += `${comparison.coverage}\n\n`;
  }
  if (comparison.introduction) {
    md += `${comparison.introduction}\n\n`;
  }

  if (comparison.insights && comparison.insights.length > 0) {
    md += '### Comparative insights\n\n';
    for (const insight of comparison.insights) {
      md += `- **${insight.title}**: ${insight.text}\n`;
    }
  }

  return marked.parse(md) as string;
};
