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
 * select the target. Minimizes camera movement: only zooms out if the cards
 * don't fit at the current zoom, and only pans the minimum distance needed to
 * bring both cards into view.
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

  /**
   * Animate the camera the minimum amount needed to bring `bounds` fully into
   * view (with gutter padding). Only zooms out if the bounds don't fit at the
   * current zoom level; only pans the minimum distance on each axis.
   */
  const animateMinimalMovement = (bounds: Box, gutter: number) => {
    const screenBounds = editor.getViewportScreenBounds();
    const currentZoom = editor.getZoomLevel();

    // Determine whether we need to zoom out to fit the bounds
    const requiredScreenW = bounds.w * currentZoom + gutter * 2;
    const requiredScreenH = bounds.h * currentZoom + gutter * 2;
    const fitsAtCurrentZoom =
      requiredScreenW <= screenBounds.width &&
      requiredScreenH <= screenBounds.height;

    let targetZoom: number;
    if (fitsAtCurrentZoom) {
      targetZoom = currentZoom;
    } else {
      // Compute the minimum zoom that fits the bounds with gutter
      const fitZoom = Math.min(
        (screenBounds.width - gutter * 2) / bounds.w,
        (screenBounds.height - gutter * 2) / bounds.h,
      );
      // Cap so the displayed zoom never exceeds FOCUS_ZOOM_DISPLAY_CAP%
      const maxZoom = mapRange(
        FOCUS_ZOOM_DISPLAY_CAP,
        ZOOM_DISPLAY_RANGE[0],
        ZOOM_DISPLAY_RANGE[1],
        MIN_ZOOM,
        MAX_ZOOM,
      );
      targetZoom = Math.max(Math.min(fitZoom, maxZoom), MIN_ZOOM);
    }

    // Viewport dimensions in page coordinates at the target zoom
    const vpW = screenBounds.width / targetZoom;
    const vpH = screenBounds.height / targetZoom;

    // Gutter expressed in page coordinates
    const gutterPage = gutter / targetZoom;

    // The page-space region that must be visible (bounds + gutter padding)
    const reqMinX = bounds.minX - gutterPage;
    const reqMaxX = bounds.maxX + gutterPage;
    const reqMinY = bounds.minY - gutterPage;
    const reqMaxY = bounds.maxY + gutterPage;

    // Start from the current viewport center — preserves view context when
    // zoom changes (the viewport expands equally around the current center)
    const currentViewport = editor.getViewportPageBounds();
    let cx = currentViewport.center.x;
    let cy = currentViewport.center.y;

    // Neutral viewport at target zoom, anchored on current center
    const neutralMinX = cx - vpW / 2;
    const neutralMaxX = cx + vpW / 2;
    const neutralMinY = cy - vpH / 2;
    const neutralMaxY = cy + vpH / 2;

    // Shift X axis — only the minimum needed to contain the required region
    if (reqMinX < neutralMinX) {
      cx += reqMinX - neutralMinX;
    } else if (reqMaxX > neutralMaxX) {
      cx += reqMaxX - neutralMaxX;
    }

    // Shift Y axis — only the minimum needed to contain the required region
    if (reqMinY < neutralMinY) {
      cy += reqMinY - neutralMinY;
    } else if (reqMaxY > neutralMaxY) {
      cy += reqMaxY - neutralMaxY;
    }

    // Convert viewport center → tldraw camera coordinates
    const cameraX = vpW / 2 - cx;
    const cameraY = vpH / 2 - cy;

    editor.setCamera(
      { x: cameraX, y: cameraY, z: targetZoom },
      { animation: KEEP_IN_VIEW_ANIMATION },
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

    // Compute bounding box that contains both source and target (or just target)
    const combined = sourceBounds
      ? new Box(
          Math.min(sourceBounds.minX, targetBounds.minX),
          Math.min(sourceBounds.minY, targetBounds.minY),
          Math.max(sourceBounds.maxX, targetBounds.maxX) -
            Math.min(sourceBounds.minX, targetBounds.minX),
          Math.max(sourceBounds.maxY, targetBounds.maxY) -
            Math.min(sourceBounds.minY, targetBounds.minY),
        )
      : targetBounds;

    // If the combined box can fit on screen, move minimally to show both.
    // Otherwise fall back to showing just the target with minimal movement.
    if (canFitWithinZoomCap(editor, combined, gutter)) {
      animateMinimalMovement(combined, gutter);
    } else {
      animateMinimalMovement(targetBounds, gutter);
    }

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
