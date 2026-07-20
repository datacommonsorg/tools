import { createShapeId, type Editor } from 'tldraw';
import { useAtlasStore } from '~/store';
import { KEEP_IN_VIEW_ANIMATION } from './config';

/**
 * When the store's `focusTarget` is set, pan the camera to that shape and
 * select it. If the shape doesn't exist yet (new chart still being created
 * through the async sync pipeline), wait for it to appear via a one-shot
 * afterCreate handler.
 * Returns the cleanup that unsubscribes the watcher.
 */
export const registerCardFocus = (editor: Editor): (() => void) => {
  let cleanupAfterCreate: (() => void) | null = null;

  const focusOnShape = (shapeId: ReturnType<typeof createShapeId>) => {
    const bounds = editor.getShapePageBounds(shapeId);
    if (!bounds) return;

    editor.centerOnPoint(bounds.center, {
      animation: KEEP_IN_VIEW_ANIMATION,
    });

    editor.select(shapeId);
  };

  const unsubscribe = useAtlasStore.subscribe(
    (state) => state.focusTarget,
    (focusTarget) => {
      if (!focusTarget) return;

      // Clear any pending afterCreate from a previous focus
      cleanupAfterCreate?.();
      cleanupAfterCreate = null;

      const rawId = focusTarget.replace(/^shape:/, '');
      const shapeId = createShapeId(rawId);

      if (editor.getShapePageBounds(shapeId)) {
        // Shape already exists — focus immediately
        focusOnShape(shapeId);
      } else {
        // Shape not yet on canvas — wait for it to be created
        cleanupAfterCreate = editor.sideEffects.registerAfterCreateHandler(
          'shape',
          (shape) => {
            if (shape.id === shapeId) {
              cleanupAfterCreate?.();
              cleanupAfterCreate = null;
              focusOnShape(shapeId);
            }
          },
        );
      }

      useAtlasStore.getState().cardClearFocusTarget();
    },
  );

  return () => {
    unsubscribe();
    cleanupAfterCreate?.();
  };
};
