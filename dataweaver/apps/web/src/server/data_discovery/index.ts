import type { Content } from '@google/genai';
import { getServiceConfig, getSkillConfig } from '~/server/config';
import { getGenAI } from '~/server/gemini';
import { callMcp } from '~/server/mcp';
import type {
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

  const placeClause = `\n\nTARGET PLACE: "${place}" — all variables MUST be relevant to this location.`;
  const systemInstruction =
    skill.systemPrompt + atlasClause + dateRangeClause + placeClause;

  // Build messages
  const messages: Content[] = [
    {
      role: 'user',
      parts: [
        {
          text: `Find statistical variables for "${place}" related to: "${query}"`,
        },
      ],
    },
  ];

  // Tool-calling loop
  let toolCallCount = 0;
  while (!signal?.aborted && toolCallCount < maxToolCalls) {
    const response = await genAI.models.generateContent({
      model: config.models.dataDiscovery,
      contents: messages,
      config: { tools: geminiTools, systemInstruction },
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

        const toolResult = await callMcp<McpToolCallResult>(
          'tools/call',
          { name: fcName, arguments: fc?.args },
          signal,
        );

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
