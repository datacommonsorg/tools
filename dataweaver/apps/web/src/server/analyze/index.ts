import { getServiceConfig, getSkillConfig } from '~/server/config';
import { getGenAI } from '~/server/gemini';
import type { QueryAnalysis } from '~/server/types';

interface AnalyzeParams {
  query: string;
  atlasContext: string;
}

/**
 * Calls the analyze skill to extract places, topic, titles, and date range
 * from a natural-language query. Returns a structured QueryAnalysis.
 */
export const analyzeQuery = async (
  params: AnalyzeParams,
): Promise<QueryAnalysis> => {
  const { query, atlasContext } = params;
  const config = getServiceConfig();
  const skill = getSkillConfig('analyze');
  const genAI = getGenAI();

  const atlasHint = atlasContext ? `\nAtlas context: ${atlasContext}` : '';
  const systemPrompt = skill.systemPrompt + atlasHint;

  const response = await genAI.models.generateContent({
    model: config.models.analyze,
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
