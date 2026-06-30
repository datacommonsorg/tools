import { extractJson } from '~/functions/extract_json';
import { getGenAI } from '~/server/clients/gemini';
import { getServiceConfig, getSkillConfig } from '~/server/config';
import type { FollowUpContext, ParsedQuery } from '~/server/types';

interface ParseQueryParams {
  query: string;
  atlasContext: string;
  ancestorChainLength: number;
  followUpContext?: FollowUpContext;
}

/**
 * Parses a natural-language query into structured parameters (places, topic,
 * titles, date range) for downstream Data Commons MCP calls.
 */
export const parseQuery = async (
  params: ParseQueryParams,
): Promise<ParsedQuery> => {
  const { query, atlasContext, ancestorChainLength, followUpContext } = params;
  const config = getServiceConfig();
  const skill = getSkillConfig('parse_query');
  const genAI = getGenAI();

  const hasHistory = ancestorChainLength > 0;
  const historyHint = hasHistory
    ? `\nPrevious conversation context exists (${ancestorChainLength} exchanges). The user may be asking a follow-up.`
    : '';
  const atlasHint = atlasContext ? `\nAtlas context: ${atlasContext}` : '';
  const systemPrompt = skill.systemPrompt + historyHint + atlasHint;

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

  const parsed = extractJson<ParsedQuery>(responseText);

  return parsed
    ? {
        places: Array.isArray(parsed.places) ? parsed.places : [query],
        topic: parsed.topic || query,
        titles: parsed.titles || {},
        isFollowUp: !!parsed.isFollowUp || !!followUpContext,
        dateRange: parsed.dateRange || undefined,
      }
    : {
        places: [query],
        topic: query,
        titles: {},
        isFollowUp: !!followUpContext,
      };
};
