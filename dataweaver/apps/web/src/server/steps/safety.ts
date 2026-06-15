import { extractJson } from '~/functions/extract_json';
import { getGenAI } from '~/server/clients/gemini';
import { getServiceConfig, getSkillConfig } from '~/server/config';

const regexCache = new Map<string, RegExp>();

interface SafetyResult {
  allowed: boolean;
  reason?: string;
}

/**
 * Layered prompt safety check:
 * 1. Regex patterns (instant, zero-cost) — catches obvious injection attempts
 * 2. Fast LLM classification — catches subtle/novel attacks
 */
export const checkPromptSafety = async (
  query: string,
): Promise<SafetyResult> => {
  const skill = getSkillConfig('safety');

  // Layer 1: Regex pattern matching
  if (skill.regexPatterns) {
    for (const pattern of skill.regexPatterns) {
      let regex = regexCache.get(pattern);
      if (!regex) {
        regex = new RegExp(pattern, 'i');
        regexCache.set(pattern, regex);
      }
      if (regex.test(query)) {
        return {
          allowed: false,
          reason: 'Query matched a disallowed pattern.',
        };
      }
    }
  }

  // Layer 2: LLM classification for ambiguous cases
  // Skip LLM check for very short/simple queries (optimization)
  if (query.length < 12) return { allowed: true };

  try {
    const config = getServiceConfig();
    const genAI = getGenAI();

    const response = await genAI.models.generateContent({
      model: config.models.safety,
      contents: `${skill.systemPrompt}\n\n"${query}"`,
    });

    const responseText = response.text || '';
    const parsed = extractJson<SafetyResult>(responseText);
    if (parsed?.allowed === false) {
      return {
        allowed: false,
        reason: parsed.reason || 'Blocked by safety classifier.',
      };
    }
    // If LLM response is unparseable, allow (fail-open for legitimate queries)
  } catch (err) {
    // If safety LLM call fails, allow the query through (fail-open)
    // Log for monitoring in production
    console.warn('[safety] LLM safety check failed, allowing query:', err);
  }

  return { allowed: true };
};
