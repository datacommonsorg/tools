import { STATUS } from '~/server/types';
import { useAtlasStore } from '~/store';

/** Current version of the serialized state format. */
export const STATE_VERSION = 1;

/** Import failure with enough detail for the UI to explain what went wrong. */
export class ImportError extends Error {
  constructor(
    readonly reason: 'malformed' | 'version-mismatch',
    message: string,
  ) {
    super(message);
    this.name = 'ImportError';
  }
}

interface StateEnvelope {
  version: typeof STATE_VERSION;
  exportedAt: string;
  state: {
    nodes: ReturnType<typeof useAtlasStore.getState>['nodes'];
    latestNodeId: ReturnType<typeof useAtlasStore.getState>['latestNodeId'];
    cards: ReturnType<typeof useAtlasStore.getState>['cards'];
  };
}

/** Export the current persistent store state as a downloaded JSON file. */
export const exportState = (): void => {
  const { nodes, latestNodeId, cards } = useAtlasStore.getState();

  const envelope: StateEnvelope = {
    version: STATE_VERSION,
    exportedAt: new Date().toISOString(),
    state: { nodes, latestNodeId, cards },
  };

  const blob = new Blob([JSON.stringify(envelope, null, 2)], {
    type: 'application/json',
  });
  const url = URL.createObjectURL(blob);
  const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
  const a = document.createElement('a');
  a.href = url;
  a.download = `atlas-state-${timestamp}.json`;
  a.click();
  URL.revokeObjectURL(url);
};

/** Import a previously-exported JSON file and replace the current store state. */
export const importState = async (file: File): Promise<void> => {
  const text = await file.text();

  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    throw new ImportError('malformed', 'File is not valid JSON.');
  }

  if (typeof parsed !== 'object' || parsed === null) {
    throw new ImportError('malformed', 'Parsed JSON is not an object.');
  }

  const parsedObject = parsed as Record<string, unknown>;
  const parsedVersion =
    typeof parsedObject.version === 'number' ? parsedObject.version : undefined;

  // A missing/non-numeric version is malformed JSON, not a genuine mismatch.
  if (parsedVersion === undefined) {
    throw new ImportError('malformed', 'Export is missing a numeric version.');
  }

  if (parsedVersion !== STATE_VERSION) {
    throw new ImportError(
      'version-mismatch',
      `This file was exported from version ${parsedVersion}. The canvas expects version ${STATE_VERSION}.`,
    );
  }

  if (!hasValidState(parsedObject)) {
    throw new ImportError(
      'malformed',
      'State payload is missing required slices.',
    );
  }

  // Clear transient UI and replace persistent slices atomically.
  useAtlasStore.setState({
    nodes: parsedObject.state.nodes,
    latestNodeId: parsedObject.state.latestNodeId,
    cards: parsedObject.state.cards,
    isProcessing: false,
    currentStatus: STATUS.complete,
  });
};

/** Shape check for the payload; the version is validated separately. */
const hasValidState = (value: object): value is StateEnvelope => {
  const state = (value as Record<string, unknown>).state;
  if (typeof state !== 'object' || state === null) return false;
  const slices = state as Record<string, unknown>;
  return (
    typeof slices.nodes === 'object' &&
    slices.nodes !== null &&
    typeof slices.cards === 'object' &&
    slices.cards !== null &&
    (slices.latestNodeId === null || typeof slices.latestNodeId === 'string')
  );
};
