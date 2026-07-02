// TODO(scott): Extract the multi-step query workflow into a
// dedicated orchestrator service (e.g., src/server/query_orchestrator.ts),
// leaving the API route as a minimal HTTP/SSE transport wrapper.

import { nanoid } from 'nanoid';
import type { NextRequest } from 'next/server';
import { extractJson } from '~/functions/extract_json';
import { fetchGeminiTools, runToolLoop } from '~/server/steps/data_discovery';
import { fetchTimeSeries } from '~/server/steps/observations';
import { parseQuery } from '~/server/steps/parse_query';
import { renderResultHtml } from '~/server/steps/render_result_html';
import { checkPromptSafety } from '~/server/steps/safety';
import {
  type FollowUp,
  type Insight,
  type QueryResult,
  type QueryStreamRequest,
  STATUS,
  STREAM_EVENT,
  type StreamEvent,
} from '~/server/types';

interface QueryModelResponse {
  placeDcid?: string;
  placeName?: string;
  coverage?: string;
  introduction?: string;
  variables?: Array<{ dcid: string; name: string; rationale?: string }>;
  insights?: Insight[];
  relatedQueries?: string[];
  followUp?: FollowUp;
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

  const query = body?.query;
  const atlasContext =
    typeof body?.atlasContext === 'string' ? body.atlasContext : '';
  const ancestorChain = Array.isArray(body?.ancestorChain)
    ? body.ancestorChain
    : [];
  const selectedEntityDcids = Array.isArray(body?.selectedEntityDcids)
    ? body.selectedEntityDcids
    : [];
  const followUpContext = body?.followUpContext ?? undefined;

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
          message: STATUS.checkingSafety,
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

        // ─── Analyze query ────────────────────────────────────────────────
        emit({ type: STREAM_EVENT.status, message: STATUS.parsingQuery });
        const parsed = await parseQuery({
          query,
          atlasContext,
          ancestorChainLength: ancestorChain.length,
          followUpContext,
        });

        // Resolve places
        let places = parsed.places;
        if (parsed.isFollowUp && places.length === 0) {
          places = selectedEntityDcids.length > 0 ? selectedEntityDcids : [];
        }
        const noExplicitPlace = places.length === 0;
        if (noExplicitPlace) places = ['Earth'];

        emit({ type: STREAM_EVENT.parsedQuery, data: parsed });
        if (signal.aborted) {
          controller.close();
          return;
        }

        // ─── Data Discovery ──────────────────────────────────────────────────

        // Fetch tools
        emit({
          type: STREAM_EVENT.status,
          message: STATUS.fetchingTools,
        });
        const geminiTools = await fetchGeminiTools(signal);

        // Process each place
        for (let i = 0; i < places.length; i++) {
          if (signal.aborted) break;

          const place = places[i];
          if (!place?.trim()) {
            emit({
              type: STREAM_EVENT.placeSkipped,
              place: place ?? '',
              reason: 'Empty place name',
            });
            continue;
          }

          const placeLabel = parsed.titles[place] || place;
          emit({
            type: STREAM_EVENT.status,
            message: STATUS.discoveringMetrics(
              placeLabel,
              i + 1,
              places.length,
            ),
          });

          // Run Gemini tool loop
          const { text: responseText, resolvedPlaceDcid } = await runToolLoop({
            place,
            query,
            parsed,
            atlasContext,
            ancestorChain,
            followUpContext,
            noExplicitPlace,
            geminiTools,
            signal,
            onToolCall: (e) => {
              emit({ type: STREAM_EVENT.toolCall, tool: e.tool, args: e.args });
              emit({
                type: STREAM_EVENT.status,
                message: STATUS.usingTool(e.tool, e.count, e.max),
              });
            },
          });

          if (signal.aborted) break;
          if (!responseText) {
            emit({
              type: STREAM_EVENT.placeSkipped,
              place,
              reason: STATUS.noResponse(placeLabel),
            });
            continue;
          }
          // Parse model response into query results
          emit({
            type: STREAM_EVENT.status,
            message: STATUS.buildingResults(placeLabel),
          });
          let parsedResponse: QueryModelResponse | undefined;
          try {
            parsedResponse = extractJson<QueryModelResponse>(responseText);
            if (!parsedResponse) {
              throw new Error('No JSON object found in response');
            }
            if (typeof parsedResponse !== 'object') {
              throw new Error('Invalid JSON object');
            }
          } catch {
            emit({
              type: STREAM_EVENT.placeSkipped,
              place,
              reason: STATUS.invalidResponse(placeLabel),
            });
            continue;
          }
          const variables = parsedResponse.variables || [];
          if (variables.length === 0 && !parsedResponse.followUp) {
            emit({
              type: STREAM_EVENT.placeSkipped,
              place,
              reason: STATUS.noVariables(placeLabel),
            });
            continue;
          }
          const entityDcid = parsedResponse.placeDcid || resolvedPlaceDcid;
          if (!entityDcid && !parsedResponse.followUp) {
            emit({
              type: STREAM_EVENT.placeSkipped,
              place,
              reason: STATUS.invalidDcid(placeLabel),
            });
            continue;
          }

          // Fetch time-series observations for each variable
          emit({
            type: STREAM_EVENT.status,
            message: STATUS.loadingTimeSeries(placeLabel, variables.length),
          });

          const timeSeries = entityDcid
            ? await Promise.all(
                variables.map((v) =>
                  fetchTimeSeries(v.dcid, entityDcid, signal),
                ),
              )
            : [];
          const entities = entityDcid
            ? [{ dcid: entityDcid, name: parsedResponse.placeName || place }]
            : [];
          const discoveryResult: QueryResult = {
            id: nanoid(),
            title:
              parsed.titles[place] ||
              `Metrics for ${parsedResponse.placeName || place}`,
            variables: variables.map((v) => ({
              dcid: v.dcid,
              name: v.name,
              rationale: v.rationale,
            })),
            entities,
            timeSeries,
            dateRange: parsed.dateRange,
            introduction: parsedResponse.introduction,
            coverage: parsedResponse.coverage,
            insights: parsedResponse.insights,
            relatedQueries: parsedResponse.relatedQueries,
            followUp:
              variables.length === 0 ? parsedResponse.followUp : undefined,
          };

          // Strip follow-up options when no explicit place was provided —
          // the question should only ask the user to specify a place.
          if (noExplicitPlace && discoveryResult.followUp) {
            discoveryResult.followUp.options = [];
          }

          const { tableHtml, notesHtml } = renderResultHtml(discoveryResult);
          discoveryResult.tableHtml = tableHtml;
          discoveryResult.notesHtml = notesHtml;

          emit({
            type: STREAM_EVENT.queryResult,
            result: discoveryResult,
            place,
          });
        }

        emit({ type: STREAM_EVENT.complete, message: STATUS.complete });
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
