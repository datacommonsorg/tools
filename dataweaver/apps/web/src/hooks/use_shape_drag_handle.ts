import { type PointerEvent as ReactPointerEvent, useCallback } from 'react';
import { type TLShapeId, useEditor } from 'tldraw';

/**
 * Returns a `pointerdown` handler that turns an element into a drag handle for
 * one or more shapes.
 *
 * @param getShapeIds - Resolves which shapes the press should drag. Called once
 * per pointerdown, so it can also run side effects (e.g. selecting the pressed
 * shape) before the drag begins.
 * @param historyLabel - History label for the drag. The start marker uses it
 * verbatim; the end marker appends `-end`.
 */
export const useShapeDragHandle = (
  getShapeIds: () => TLShapeId[],
  historyLabel: string,
) => {
  const editor = useEditor();

  return useCallback(
    (event: ReactPointerEvent<HTMLDivElement>) => {
      // Prevent the event from bubbling to the canvas
      event.stopPropagation();

      // Ignore if trigger was not primary button drags
      if (event.button !== 0) return;

      const origins = getShapeIds().flatMap((id) => {
        const shape = editor.getShape(id);
        if (!shape) return [];
        return [{ id: shape.id, type: shape.type, x: shape.x, y: shape.y }];
      });
      if (origins.length === 0) return;

      editor.markHistoryStoppingPoint(historyLabel);

      const zoom = editor.getZoomLevel();
      const originClientX = event.clientX;
      const originClientY = event.clientY;

      const target = event.currentTarget;
      target.setPointerCapture(event.pointerId);

      // Show the dragging cursor during drag. Note: we're matching the cursor
      // TLDraw uses for its own drag handles
      const previousCursor = target.style.cursor;
      target.style.cursor = 'all-scroll';

      const dragged = (moveEvent: PointerEvent) => {
        moveEvent.stopPropagation();
        const deltaX = (moveEvent.clientX - originClientX) / zoom;
        const deltaY = (moveEvent.clientY - originClientY) / zoom;

        editor.updateShapes(
          origins.map((origin) => ({
            id: origin.id,
            type: origin.type,
            x: origin.x + deltaX,
            y: origin.y + deltaY,
          })),
        );
      };

      const stoppedDragging = (endEvent: PointerEvent) => {
        if (target.hasPointerCapture(endEvent.pointerId)) {
          target.releasePointerCapture(endEvent.pointerId);
        }

        // Restore the cursor to what it was before the drag started
        target.style.cursor = previousCursor;

        target.removeEventListener('pointermove', dragged);
        target.removeEventListener('pointerup', stoppedDragging);
        target.removeEventListener('pointercancel', stoppedDragging);
        target.removeEventListener('lostpointercapture', stoppedDragging);
        editor.markHistoryStoppingPoint(`${historyLabel}-end`);
      };

      target.addEventListener('pointermove', dragged);
      target.addEventListener('pointerup', stoppedDragging);
      target.addEventListener('pointercancel', stoppedDragging);
      target.addEventListener('lostpointercapture', stoppedDragging);
    },
    [editor, getShapeIds, historyLabel],
  );
};
