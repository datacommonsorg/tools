import { Box, type Editor, type TLShapeId } from 'tldraw';
import { mapRange } from '~/functions/map_range';
import { useAtlasStore } from '~/store';
import {
  FOCUS_ZOOM_DISPLAY_CAP,
  KEEP_IN_VIEW_ANIMATION,
  MAX_ZOOM,
  MIN_ZOOM,
  ZOOM_DISPLAY_RANGE,
} from './config';
import { canFitWithinZoomCap, resolveGrid } from './register_card_placement';

/**
 * When the store's `focusTarget` is set, move the camera so both the source
 * card (that triggered the action) and the target card are visible, then
 * select the target. If the target is already fully in view, just select it
 * without moving the camera.
 *
 * If the shape doesn't exist yet (new chart still being created through the
 * async sync pipeline), wait for it to appear via a one-shot afterCreate
 * handler.
 *
 * Returns the cleanup that unsubscribes the watcher.
 */
export const registerCardFocus = (editor: Editor): (() => void) => {
  let cleanupAfterCreate: (() => void) | null = null;

  const isFullyInView = (shapeId: TLShapeId): boolean => {
    const bounds = editor.getShapePageBounds(shapeId);
    if (!bounds) return false;
    const viewport = editor.getViewportPageBounds();
    return (
      bounds.minX >= viewport.minX &&
      bounds.minY >= viewport.minY &&
      bounds.maxX <= viewport.maxX &&
      bounds.maxY <= viewport.maxY
    );
  };

  const focusOnShape = (targetId: TLShapeId, sourceId: TLShapeId) => {
    const targetBounds = editor.getShapePageBounds(targetId);
    if (!targetBounds) return;

    // If the target is already fully visible, just select — no camera move
    if (isFullyInView(targetId)) {
      editor.select(targetId);
      return;
    }

    const sourceBounds = editor.getShapePageBounds(sourceId);
    const gutter = resolveGrid(editor).gutter;

    if (sourceBounds) {
      // Compute bounding box that contains both source and target
      const combined = new Box(
        Math.min(sourceBounds.minX, targetBounds.minX),
        Math.min(sourceBounds.minY, targetBounds.minY),
        Math.max(sourceBounds.maxX, targetBounds.maxX) -
          Math.min(sourceBounds.minX, targetBounds.minX),
        Math.max(sourceBounds.maxY, targetBounds.maxY) -
          Math.min(sourceBounds.minY, targetBounds.minY),
      );

      if (canFitWithinZoomCap(editor, combined, gutter)) {
        // Compute the zoom that fits both cards with gutter padding on
        // each side, then cap so the displayed zoom never exceeds {FOCUS_ZOOM_DISPLAY_CAP}%.
        const maxZoom = mapRange(
          FOCUS_ZOOM_DISPLAY_CAP,
          ZOOM_DISPLAY_RANGE[0],
          ZOOM_DISPLAY_RANGE[1],
          MIN_ZOOM,
          MAX_ZOOM,
        );
        const screenBounds = editor.getViewportScreenBounds();
        const fitZoom = Math.min(
          (screenBounds.width - gutter * 2) / combined.w,
          (screenBounds.height - gutter * 2) / combined.h,
        );

        editor.zoomToBounds(combined, {
          animation: KEEP_IN_VIEW_ANIMATION,
          targetZoom: Math.min(fitZoom, maxZoom),
        });
        editor.select(targetId);
        return;
      }
    }

    // Fallback: source missing or combined box too large for zoom cap
    editor.centerOnPoint(targetBounds.center, {
      animation: KEEP_IN_VIEW_ANIMATION,
    });
    editor.select(targetId);
  };

  const unsubscribe = useAtlasStore.subscribe(
    (state) => state.focusTarget,
    (focusTarget) => {
      if (!focusTarget) return;

      // Clear any pending afterCreate from a previous focus
      cleanupAfterCreate?.();
      cleanupAfterCreate = null;

      const targetId = focusTarget.shapeId as TLShapeId;
      const sourceId = focusTarget.sourceShapeId as TLShapeId;

      if (editor.getShapePageBounds(targetId)) {
        // Shape already exists — focus immediately
        focusOnShape(targetId, sourceId);
      } else {
        let isDisposed = false;
        let cleanup: (() => void) | null = null;
        // Shape not yet on canvas — wait for it to be created
        cleanup = editor.sideEffects.registerAfterCreateHandler(
          'shape',
          (shape) => {
            if (shape.id === targetId && !isDisposed) {
              isDisposed = true;
              cleanup?.();
              focusOnShape(targetId, sourceId);
            }
          },
        );
        cleanupAfterCreate = () => {
          isDisposed = true;
          cleanup?.();
        };
      }

      useAtlasStore.getState().cardClearFocusTarget();
    },
  );

  return () => {
    unsubscribe();
    cleanupAfterCreate?.();
  };
};
