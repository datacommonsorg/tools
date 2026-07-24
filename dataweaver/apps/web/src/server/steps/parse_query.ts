import { extractJson } from '~/functions/extract_json';
import { getGenAI } from '~/server/clients/gemini';
import { getServiceConfig, getSkillConfig } from '~/server/config';
import type {
  ChartStyle,
  FollowUp,
  FollowUpContext,
  ParsedQuery,
} from '~/server/types';

interface ParseQueryParams {
  query: string;
  atlasContext: string;
  ancestorChainLength: number;
  followUpContext?: FollowUpContext;
  hasChartSelection?: boolean;
}

/**
 * Parses a natural-language query into structured parameters (places, topic,
 * titles, date range) for downstream Data Commons MCP calls.
 */
export const parseQuery = async (
  params: ParseQueryParams,
): Promise<ParsedQuery> => {
  const {
    query,
    atlasContext,
    ancestorChainLength,
    followUpContext,
    hasChartSelection,
  } = params;
  const config = getServiceConfig();
  const skill = getSkillConfig('parse_query');
  const genAI = getGenAI();

  const hasHistory = ancestorChainLength > 0;
  const historyHint = hasHistory
    ? `\nPrevious conversation context exists (${ancestorChainLength} exchanges). Only mark isFollowUp=true if the query is clearly a continuation that lacks its own place or topic. If the query explicitly mentions a place or topic, treat it as a new independent query and extract places/topic normally.`
    : '';
  const atlasHint = atlasContext ? `\nAtlas context: ${atlasContext}` : '';
  const chartHint = hasChartSelection
    ? '\nCharts selected: The user currently has chart card(s) selected on the canvas.'
    : '';
  const systemPrompt = skill.systemPrompt + historyHint + atlasHint + chartHint;

  // When followUpContext is present, include the original query and Q&A chain
  // so the model can extract places/topic from the full conversation.
  let contents: string;
  if (followUpContext) {
    const chain = followUpContext.followUps
      .map((f) => `Q: "${f.question}" → A: "${f.answer}"`)
      .join('\n');
    contents = `Original query: "${followUpContext.originalQuery}"\nFollow-up clarifications:\n${chain}\n\nCurrent query: "${query}"`;
  } else {
    contents = `Query: "${query}"`;
  }

  const response = await genAI.models.generateContent({
    model: config.models.parseQuery,
    contents,
    config: { systemInstruction: systemPrompt },
  });

  const responseText = response.text || '';

  const VALID_CHART_STYLES: ChartStyle[] = [
    'bar-vertical',
    'bar-horizontal',
    'line',
  ];

  const parsed = extractJson<
    ParsedQuery & {
      followUp?: FollowUp;
      chartStyleIntent?: { targetStyle: string };
    }
  >(responseText);

  if (!parsed) {
    return {
      places: [query],
      topic: query,
      titles: {},
      isFollowUp: !!followUpContext,
    };
  }

  // Validate chartStyleIntent if present
  const chartStyleIntent =
    parsed.chartStyleIntent?.targetStyle &&
    VALID_CHART_STYLES.includes(
      parsed.chartStyleIntent.targetStyle as ChartStyle,
    )
      ? { targetStyle: parsed.chartStyleIntent.targetStyle as ChartStyle }
      : undefined;

  return {
    places: Array.isArray(parsed.places) ? parsed.places : [query],
    topic: parsed.topic || query,
    titles: parsed.titles || {},
    isFollowUp: !!parsed.isFollowUp || !!followUpContext,
    dateRange: parsed.dateRange || undefined,
    followUp: parsed.followUp || undefined,
    chartStyleIntent,
  };
};
