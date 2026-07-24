import type { NextRequest } from 'next/server';
import {
  buildPlaceSummaries,
  comparePlaces,
} from '~/server/steps/compare_places';
import { renderComparisonHtml } from '~/server/steps/render_result_html';
import {
  type CombineStreamRequest,
  type QueryResult,
  STATUS,
  STREAM_EVENT,
  type StreamEvent,
} from '~/server/types';

export async function POST(request: NextRequest) {
  let body: CombineStreamRequest;
  try {
    body = await request.json();
  } catch {
    return new Response(JSON.stringify({ error: 'Invalid JSON body' }), {
      status: 400,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  const query = body?.query;
  const results: QueryResult[] = Array.isArray(body?.results)
    ? body.results
    : [];

  if (typeof query !== 'string' || !query.trim()) {
    return new Response(JSON.stringify({ error: 'Missing or invalid query' }), {
      status: 400,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  if (results.length < 2) {
    return new Response(
      JSON.stringify({ error: 'At least 2 results are required to combine' }),
      { status: 400, headers: { 'Content-Type': 'application/json' } },
    );
  }

  // Derive a topic from the variable names across all results.
  const variableNames = [
    ...new Set(results.flatMap((r) => r.variables.map((v) => v.name))),
  ];
  const topic = variableNames.join(', ') || 'Data comparison';

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
        emit({
          type: STREAM_EVENT.status,
          message: STATUS.comparingPlaces,
        });

        const summaries = buildPlaceSummaries(results);
        const comparisonResult = await comparePlaces({
          query,
          topic,
          summaries,
        });
        comparisonResult.notesHtml = renderComparisonHtml(comparisonResult);

        if (signal.aborted) {
          controller.close();
          return;
        }

        emit({
          type: STREAM_EVENT.comparisonResult,
          result: comparisonResult,
        });

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
