import type { Content } from '@google/genai';
import { getGenAI } from '~/server/clients/gemini';
import { callMcp } from '~/server/clients/mcp';
import { getServiceConfig, getSkillConfig } from '~/server/config';
import type {
  FollowUpContext,
  McpToolCallResult,
  McpToolsListResult,
  ParsedQuery,
} from '~/server/types';

// ─── Types ──────────────────────────────────────────────────────────────────

export interface GeminiTool {
  functionDeclarations: Array<{
    name: string;
    description: string;
    parameters: Record<string, unknown>;
  }>;
}

export interface ToolCallEvent {
  tool: string;
  args: Record<string, unknown>;
  count: number;
  max: number;
}

interface ToolLoopParams {
  place: string;
  query: string;
  parsed: ParsedQuery;
  atlasContext: string;
  ancestorChain: { query: string; topic: string; places: string[] }[];
  followUpContext?: FollowUpContext;
  /** When true, no specific place was mentioned — 'Earth' is used as a default. */
  noExplicitPlace?: boolean;
  geminiTools: GeminiTool[];
  signal?: AbortSignal;
  onToolCall?: (event: ToolCallEvent) => void;
}

// ─── Public API ─────────────────────────────────────────────────────────────

/** Fetch the MCP tool list and convert to Gemini function-calling format. */
export const fetchGeminiTools = async (
  signal?: AbortSignal,
): Promise<GeminiTool[]> => {
  const result = await callMcp<McpToolsListResult>('tools/list', {}, signal);
  return result.tools.map((t) => ({
    functionDeclarations: [
      {
        name: t.name,
        description: t.description || '',
        parameters: t.inputSchema,
      },
    ],
  }));
};

export interface ToolLoopResult {
  text: string;
  resolvedPlaceDcid: string | null;
}

/**
 * Run the Gemini tool-calling loop for a single place.
 * Returns the final model text response (expected to be JSON) and the resolved
 * place DCID extracted from tool responses, or empty string/null if not found.
 */
export const runToolLoop = async (
  params: ToolLoopParams,
): Promise<ToolLoopResult> => {
  const {
    place,
    query,
    parsed,
    atlasContext,
    ancestorChain,
    followUpContext,
    geminiTools,
    signal,
    onToolCall,
  } = params;

  const config = getServiceConfig();
  const skill = getSkillConfig('data_discovery');
  const genAI = getGenAI();
  const maxToolCalls = skill.maxToolCalls || 10;

  // Track place DCID from tool responses
  let resolvedPlaceDcid: string | null = null;

  // Build system instruction
  const atlasClause = atlasContext
    ? `\n\nATLAS CONTEXT (data the user already has loaded):\n${atlasContext}\nUse this context to understand what the user has already explored.`
    : '';

  const dateRangeClause = parsed.dateRange
    ? `\n\nDATE CONSTRAINT: The user wants data limited to ${parsed.dateRange.start && parsed.dateRange.end ? `${parsed.dateRange.start} through ${parsed.dateRange.end}` : parsed.dateRange.start ? `from ${parsed.dateRange.start} onward` : `up to ${parsed.dateRange.end}`}.`
    : '';

  const placeClause = params.noExplicitPlace
    ? `\n\nTARGET PLACE: The user did not mention a specific place. Default to "Earth" (world-level) to retrieve initial data. You MUST include a followUp in your response asking which specific place or region the user would like to explore. The followUp MUST have an empty "options" array — do NOT suggest options, only provide a summary and question.`
    : `\n\nTARGET PLACE: "${place}" — all variables MUST be relevant to this location.`;
  const systemInstruction =
    skill.systemPrompt + atlasClause + dateRangeClause + placeClause;

  // Build messages with conversation history
  const messages: Content[] = [];
  if (followUpContext) {
    // Explicit follow-up disambiguation context takes priority
    const chain = followUpContext.followUps
      .map(
        (f, i) =>
          `Clarification ${i + 1}: "${f.question}" → User answered: "${f.answer}"`,
      )
      .join('\n');
    messages.push({
      role: 'user',
      parts: [
        {
          text: `FOLLOW-UP CONTEXT:\nOriginal question: "${followUpContext.originalQuery}"\n${chain}\n\nNEW REQUEST: Find statistical variables for "${place}" related to: "${query}"`,
        },
      ],
    });
  } else if (ancestorChain.length > 0) {
    const historyContext = ancestorChain
      .map(
        (node) =>
          `User asked: "${node.query}" (topic: ${node.topic}, places: ${node.places.join(', ')})`,
      )
      .join('\n');
    messages.push({
      role: 'user',
      parts: [
        {
          text: `CONVERSATION HISTORY:\n${historyContext}\n\nNEW REQUEST: Find statistical variables for "${place}" related to: "${query}"`,
        },
      ],
    });
  } else {
    messages.push({
      role: 'user',
      parts: [
        {
          text: `Find statistical variables for "${place}" related to: "${query}"`,
        },
      ],
    });
  }

  // Tool-calling loop
  let toolCallCount = 0;
  while (!signal?.aborted && toolCallCount < maxToolCalls) {
    const response = await genAI.models.generateContent({
      model: config.models.dataDiscovery,
      contents: messages,
      config: { tools: geminiTools, systemInstruction, abortSignal: signal },
    });

    if (response.functionCalls && response.functionCalls.length > 0) {
      const modelContent = response.candidates?.[0]?.content;
      if (modelContent) {
        messages.push(modelContent);
      }

      const toolResponseParts: Array<{
        functionResponse: { name: string; response: { result: unknown } };
      }> = [];

      for (const fc of response.functionCalls) {
        const fcName = fc?.name ?? 'unknown';
        toolCallCount++;
        onToolCall?.({
          tool: fcName,
          args: fc?.args as Record<string, unknown>,
          count: toolCallCount,
          max: maxToolCalls,
        });

        let toolResult: McpToolCallResult;
        try {
          toolResult = await callMcp<McpToolCallResult>(
            'tools/call',
            { name: fcName, arguments: fc?.args },
            signal,
          );
        } catch (err: unknown) {
          // If the caller aborted, re-throw so the outer loop exits cleanly.
          if (signal?.aborted) throw err;
          // Tool call timed out or failed — return empty so the place is skipped.
          return { text: '', resolvedPlaceDcid };
        }

        // Extract place DCID from search_indicators responses
        if (fcName === 'search_indicators' && !resolvedPlaceDcid) {
          try {
            const resultText = toolResult?.content?.[0]?.text;
            if (resultText) {
              const parsed = JSON.parse(resultText);
              const placesWithData =
                parsed.variables?.[0]?.places_with_data ||
                parsed.topics?.[0]?.places_with_data;
              if (placesWithData && placesWithData.length > 0) {
                resolvedPlaceDcid = placesWithData[0];
              }
            }
          } catch {
            // Ignore parsing errors — DCID extraction is best-effort
          }
        }

        toolResponseParts.push({
          functionResponse: {
            name: fcName,
            response: { result: toolResult },
          },
        });
      }

      messages.push({ role: 'tool', parts: toolResponseParts });
    } else if (response.text) {
      return { text: response.text, resolvedPlaceDcid };
    } else {
      break;
    }
  }

  return { text: '', resolvedPlaceDcid };
};
