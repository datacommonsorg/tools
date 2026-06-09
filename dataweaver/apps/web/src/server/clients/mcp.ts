import { nanoid } from 'nanoid';
import { getServiceConfig } from '~/server/config';

export const callMcp = async <T = unknown>(
  method: string,
  params: Record<string, unknown> = {},
  signal?: AbortSignal,
): Promise<T> => {
  const apiKey = process.env.DATA_COMMONS_API_KEY;
  if (!apiKey)
    throw new Error('DATA_COMMONS_API_KEY environment variable is not set');

  const config = getServiceConfig();
  const mcpEndpoint = config.api.dataCommons.mcpEndpoint;

  const payload = {
    jsonrpc: '2.0',
    id: nanoid(),
    method,
    params,
  };

  const res = await fetch(mcpEndpoint, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      // biome-ignore lint/style/useNamingConvention: HTTP header name
      Accept: 'text/event-stream, application/json',
      'X-API-Key': apiKey,
    },
    body: JSON.stringify(payload),
    signal,
  });

  if (!res.ok) {
    throw new Error(`MCP Error: ${res.status} ${res.statusText}`);
  }

  const text = await res.text();

  // Response may be SSE-formatted or plain JSON
  let dataStr = '';
  for (const line of text.split('\n')) {
    if (line.startsWith('data: ')) {
      dataStr = line.slice(6);
      break;
    }
  }
  if (!dataStr) {
    try {
      JSON.parse(text);
      dataStr = text;
    } catch {
      throw new Error(`Invalid MCP response format: ${text.substring(0, 100)}`);
    }
  }

  let data: {
    result?: T;
    error?: { message: string };
  } | null = null;

  try {
    data = JSON.parse(dataStr);
  } catch {
    throw new Error(
      `Failed to parse MCP response JSON: ${dataStr.substring(0, 100)}`,
    );
  }

  if (data && typeof data === 'object' && data.error) {
    throw new Error(data.error.message || 'Unknown MCP error');
  }

  if (data?.result === undefined) {
    throw new Error('MCP response missing result');
  }

  return data.result;
};
