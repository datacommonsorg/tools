import { STATUS } from '~/server/types';
import { useAtlasStore } from '~/store';

interface StateEnvelope {
  version: 1;
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
    version: 1,
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
  const envelope: unknown = JSON.parse(text);

  if (!isValidEnvelope(envelope)) {
    throw new Error('Invalid state file: missing required fields or version.');
  }

  // Clear transient UI and replace persistent slices atomically.
  useAtlasStore.setState({
    nodes: envelope.state.nodes,
    latestNodeId: envelope.state.latestNodeId,
    cards: envelope.state.cards,
    isProcessing: false,
    currentStatus: STATUS.complete,
  });
};

const isValidEnvelope = (value: unknown): value is StateEnvelope => {
  if (typeof value !== 'object' || value === null) return false;
  const obj = value as Record<string, unknown>;
  if (obj.version !== 1) return false;
  if (typeof obj.state !== 'object' || obj.state === null) return false;
  const state = obj.state as Record<string, unknown>;
  return (
    typeof state.nodes === 'object' &&
    state.nodes !== null &&
    typeof state.cards === 'object' &&
    state.cards !== null &&
    'latestNodeId' in state
  );
};
