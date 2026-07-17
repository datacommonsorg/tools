import type { Editor } from 'tldraw';
import { useAtlasStore } from '~/store';

/**
 * Keep the atlas store's card registry consistent with the canvas: whenever
 * a card is deleted — by the user or programmatically — it is unregistered
 * from the store. Returns the cleanup that unregisters the side effect.
 */
export const registerCardStoreSync = (editor: Editor): (() => void) => {
  return editor.sideEffects.registerAfterDeleteHandler('shape', (shape) => {
    // Ignore non-card shapes — the store only tracks cards
    if (shape.type !== 'card') return;

    useAtlasStore.getState().cardUnregister(shape.id);
  });
};
