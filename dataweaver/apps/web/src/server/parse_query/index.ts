import { getServiceConfig, getSkillConfig } from '~/server/config';
import { getGenAI } from '~/server/gemini';
import type { ParsedQuery } from '~/server/types';

interface ParseQueryParams {
  query: string;
  atlasContext: string;
}

/**
 * Parses a natural-language query into structured parameters (places, topic,
 * titles, date range) for downstream Data Commons MCP calls.
 */
export const parseQuery = async (
  params: ParseQueryParams,
): Promise<ParsedQuery> => {
  const { query, atlasContext } = params;
  const config = getServiceConfig();
  const skill = getSkillConfig('parse_query');
  const genAI = getGenAI();

  const atlasHint = atlasContext ? `\nAtlas context: ${atlasContext}` : '';
  const systemPrompt = skill.systemPrompt + atlasHint;

  const response = await genAI.models.generateContent({
    model: config.models.parseQuery,
    contents: `${systemPrompt}\n\nQuery: "${query}"\nReturn ONLY its JSON object, no markdown, no other text or explanation.`,
  });

  const text = response.text || '';
  const cleaned = text
    .replace(/```json/g, '')
    .replace(/```/g, '')
    .trim();

  try {
    const parsed = JSON.parse(cleaned);
    return {
      places: Array.isArray(parsed.places) ? parsed.places : [query],
      topic: parsed.topic || query,
      titles: parsed.titles || {},
      dateRange: parsed.dateRange || undefined,
    };
  } catch {
    return {
      places: [query],
      topic: query,
      titles: {},
    };
  }
};
