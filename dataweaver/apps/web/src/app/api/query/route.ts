import { nanoid } from 'nanoid';
import type { NextRequest } from 'next/server';
import { fetchGeminiTools, runToolLoop } from '~/server/data_discovery';
import { fetchVariableMetadata } from '~/server/observations';
import { parseQuery } from '~/server/parse_query';
import { checkPromptSafety } from '~/server/safety';
import {
  type ChartType,
  type QueryResult,
  type QueryStreamRequest,
  STREAM_EVENT,
  type StreamEvent,
} from '~/server/types';

interface QueryModelResponse {
  entityDcid?: string;
  variables?: Array<{ dcid: string; name: string; rationale?: string }>;
  suggestedChartType?: ChartType;
  summary?: string;
  insight?: string;
  followUps?: string[];
}

export async function POST(request: NextRequest) {
  let body: QueryStreamRequest;
  try {
    body = await request.json();
  } catch {
    return new Response(JSON.stringify({ error: 'Invalid JSON body' }), {
      status: 400,
      headers: { 'Content-Type': 'application/json' },
    });
  }
  const { query, atlasContext, selectedEntityDcids } = body;

  if (typeof query !== 'string' || !query.trim()) {
    return new Response(JSON.stringify({ error: 'Missing or invalid query' }), {
      status: 400,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  const encoder = new TextEncoder();
  const signal = request.signal;

  const stream = new ReadableStream({
    async start(controller) {
      const emit = (event: StreamEvent) => {
        controller.enqueue(
          encoder.encode(
            `event: ${event.type}\ndata: ${JSON.stringify(event)}\n\n`,
          ),
        );
      };

      try {
        // ─── Safety gate ──────────────────────────────────────────────────
        emit({
          type: STREAM_EVENT.status,
          message: 'Checking query safety...',
        });
        const safetyResult = await checkPromptSafety(query);
        if (!safetyResult.allowed) {
          emit({
            type: STREAM_EVENT.error,
            message:
              safetyResult.reason || 'Query was blocked by safety filter.',
          });
          controller.close();
          return;
        }

        // ─── Parse query ──────────────────────────────────────────────────
        emit({ type: STREAM_EVENT.status, message: 'Parsing query...' });
        const parsed = await parseQuery({ query, atlasContext });

        // Resolve places
        let places = parsed.places;
        if (places.length === 0) {
          places =
            selectedEntityDcids.length > 0 ? selectedEntityDcids : [query];
        }
        parsed.places = places;

        emit({ type: STREAM_EVENT.parsedQuery, data: parsed });
        if (signal.aborted) {
          controller.close();
          return;
        }

        // ─── Data Discovery ──────────────────────────────────────────────────

        // Fetch tools
        emit({
          type: STREAM_EVENT.status,
          message: 'Fetching available tools...',
        });
        const geminiTools = await fetchGeminiTools(signal);

        // Process each place
        for (let i = 0; i < places.length; i++) {
          if (signal.aborted) break;

          const place = places[i];
          if (!place?.trim()) continue;

          const placeLabel = parsed.titles[place] || place;
          emit({
            type: STREAM_EVENT.status,
            message: `Discovering metrics for ${placeLabel} (${i + 1}/${places.length})...`,
          });

          // Run Gemini tool loop
          const { text: responseText, resolvedPlaceDcid } = await runToolLoop({
            place,
            query,
            parsed,
            atlasContext,
            geminiTools,
            signal,
            onToolCall: (e) => {
              emit({ type: STREAM_EVENT.toolCall, tool: e.tool, args: e.args });
              emit({
                type: STREAM_EVENT.status,
                message: `Using tool: ${e.tool} (${e.count}/${e.max})...`,
              });
            },
          });

          if (signal.aborted) break;
          if (!responseText) {
            emit({
              type: STREAM_EVENT.status,
              message: `No response for ${placeLabel}, skipping...`,
            });
            continue;
          }

          // Parse model response into query results
          emit({
            type: STREAM_EVENT.status,
            message: `Building results for ${placeLabel}...`,
          });

          let parsedResponse: QueryModelResponse;
          try {
            const jsonMatch = responseText.match(/\{[\s\S]*\}/);
            if (!jsonMatch) {
              throw new Error('No JSON object found in response');
            }
            parsedResponse = JSON.parse(jsonMatch[0]) as QueryModelResponse;
            if (!parsedResponse || typeof parsedResponse !== 'object') {
              throw new Error('Invalid JSON object');
            }
          } catch {
            emit({
              type: STREAM_EVENT.status,
              message: `Invalid model response for ${placeLabel}, skipping...`,
            });
            continue;
          }

          const variables = parsedResponse.variables || [];
          if (variables.length === 0) {
            emit({
              type: STREAM_EVENT.status,
              message:
                parsedResponse.summary ||
                `No variables found for ${placeLabel}.`,
            });
            continue;
          }

          const entityDcid = parsedResponse.entityDcid || resolvedPlaceDcid;

          if (!entityDcid) {
            emit({
              type: STREAM_EVENT.status,
              message: `Could not resolve a valid DCID for ${placeLabel}, skipping...`,
            });
            continue;
          }

          // Fetch metadata for each variable
          emit({
            type: STREAM_EVENT.status,
            message: `Loading metadata for ${placeLabel} (${variables.length} variables)...`,
          });

          const metadata = await Promise.all(
            variables.map((v) =>
              fetchVariableMetadata(v.dcid, entityDcid, signal),
            ),
          );

          const discoveryResult: QueryResult = {
            id: nanoid(),
            chartType: parsedResponse.suggestedChartType || 'line_chart',
            title:
              parsed.titles[place] ||
              parsedResponse.summary ||
              `Metrics for ${place}`,
            variables: variables.map((v) => ({
              dcid: v.dcid,
              name: v.name,
              rationale: v.rationale,
            })),
            entities: [{ dcid: entityDcid, name: place }],
            metadata,
            dateRange: parsed.dateRange,
            summary: parsedResponse.summary,
            insight: parsedResponse.insight,
            followUps: parsedResponse.followUps,
          };

          emit({
            type: STREAM_EVENT.queryResult,
            result: discoveryResult,
            place,
          });
        }

        emit({ type: STREAM_EVENT.complete });
        controller.close();
      } catch (err: unknown) {
        if (!signal.aborted) {
          const message = err instanceof Error ? err.message : 'Unknown error';
          emit({ type: STREAM_EVENT.error, message });
        }
        controller.close();
      }
    },
  });

  return new Response(stream, {
    headers: {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache, no-transform',
      Connection: 'keep-alive',
    },
  });
}
