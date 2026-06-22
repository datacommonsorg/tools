import { marked } from 'marked';
import type { QueryResult } from '~/server/types';

/** Build the variables table as an HTML string from a query result. */
const buildTableHtml = (result: QueryResult): string => {
  const entityDcid = result.entities[0]?.dcid ?? '';
  const placeName = result.entities[0]?.name ?? '';
  const intro = result.introduction ?? '';

  let md = intro ? `${intro}\n\n` : '';
  md += '| Statistical variable | Facet(s) | Rationale |\n';
  md += '| --- | --- | --- |\n';

  for (const variable of result.variables) {
    const meta = result.metadata.find((m) => m.variableDcid === variable.dcid);
    const firstFacet = meta?.facets[0];
    const facetCell = firstFacet
      ? `${firstFacet.source}<br>${firstFacet.earliestDate} – ${firstFacet.latestDate}${firstFacet.unit ? ` · ${firstFacet.unit}` : ''}`
      : 'No data';

    const encodedVar = encodeURIComponent(variable.name);
    const encodedPlace = encodeURIComponent(placeName);
    const link = `[${variable.name}](#fetch=${variable.dcid}&place=${entityDcid}&varName=${encodedVar}&placeName=${encodedPlace})`;

    md += `| ${link} | ${facetCell} | ${variable.rationale ?? '—'} |\n`;
  }

  return marked.parse(md) as string;
};

/** Build the notes card HTML from a query result's introduction + insights. */
const buildNotesHtml = (result: QueryResult): string => {
  let md = '### About this data\n\n';
  if (result.coverage) {
    md += `${result.coverage}\n\n`;
  }
  if (result.introduction) {
    md += `${result.introduction}\n\n`;
  }

  if (result.insights && result.insights.length > 0) {
    md += '### Relevant insights\n\n';
    for (const insight of result.insights) {
      md += `- **${insight.title}**: ${insight.text}\n`;
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
