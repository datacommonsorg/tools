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

  // Combine caller's abort signal with a 30s timeout so MCP calls don't hang.
  const timeoutMs = 30_000;
  const combinedSignal = signal
    ? AbortSignal.any([signal, AbortSignal.timeout(timeoutMs)])
    : AbortSignal.timeout(timeoutMs);

  const res = await fetch(mcpEndpoint, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream, application/json',
      'X-API-Key': apiKey,
    },
    body: JSON.stringify(payload),
    signal: combinedSignal,
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

export interface McpResourceReadResult {
  contents: Array<{
    uri: string;
    mimeType?: string;
    text: string;
  }>;
}

/**
 * Read a resource from the MCP server by URI (e.g. `skill://data-commons-researcher/SKILL.md`).
 * Returns null if the resource cannot be fetched or parsed.
 */
export const readMcpResource = async (
  uri: string,
  signal?: AbortSignal,
): Promise<string | null> => {
  try {
    const result = await callMcp<McpResourceReadResult>(
      'resources/read',
      { uri },
      signal,
    );
    return result?.contents?.[0]?.text ?? null;
  } catch (err: unknown) {
    console.warn(`[mcp] Failed to read MCP resource "${uri}":`, err);
    return null;
  }
};

const _mcpSkillCache = new Map<string, Promise<string | null>>();

/**
 * Fetch and cache an MCP skill playbook (e.g. 'data-commons-researcher').
 * Returns null if unavailable or on error.
 */
export const fetchMcpSkillPlaybook = async (
  skillName: string,
): Promise<string | null> => {
  const cachedPromise = _mcpSkillCache.get(skillName);
  if (cachedPromise) return cachedPromise;

  const uri = `skill://${skillName}/SKILL.md`;
  const fetchPromise = readMcpResource(uri)
    .then((content) => {
      if (!content) {
        _mcpSkillCache.delete(skillName);
      }
      return content;
    })
    .catch((_err: unknown) => {
      _mcpSkillCache.delete(skillName);
      return null;
    });

  _mcpSkillCache.set(skillName, fetchPromise);
  return fetchPromise;
};
