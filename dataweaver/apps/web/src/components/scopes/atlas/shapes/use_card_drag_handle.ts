import { type PointerEvent as ReactPointerEvent, useCallback } from 'react';
import type { Editor, TLShapeId } from 'tldraw';

/**
 * Returns a `pointerdown` handler that turns an element into a drag handle for
 * a card shape.
 *
 * The card's actions bar sits *above* the card, outside the shape's geometry,
 * so tldraw can't drag it natively — a press there hit-tests as empty canvas
 * and starts a selection brush instead. This drives the move directly: it
 * translates the shape by the pointer delta (screen space converted to page
 * space via the zoom) for the duration of the press, using pointer capture so
 * the drag follows the cursor even when it leaves the handle.
 */
export const useCardDragHandle = (editor: Editor, shapeId: TLShapeId) =>
  useCallback(
    (event: ReactPointerEvent<HTMLDivElement>) => {
      // Ignore if trigger was not primary button drags
      if (event.button !== 0) return;

      // Prevent the event from bubbling to the canvas
      event.stopPropagation();

      const shape = editor.getShape(shapeId);
      if (!shape) return;

      editor.select(shapeId);
      editor.markHistoryStoppingPoint('drag-card');

      const zoom = editor.getZoomLevel();
      const originClientX = event.clientX;
      const originClientY = event.clientY;
      const { x: originX, y: originY } = shape;

      const target = event.currentTarget;
      target.setPointerCapture(event.pointerId);

      const dragged = (moveEvent: PointerEvent) => {
        moveEvent.stopPropagation();
        editor.updateShape({
          id: shapeId,
          type: 'card',
          x: originX + (moveEvent.clientX - originClientX) / zoom,
          y: originY + (moveEvent.clientY - originClientY) / zoom,
        });
      };

      const stoppedDragging = (endEvent: PointerEvent) => {
        if (target.hasPointerCapture(endEvent.pointerId)) {
          target.releasePointerCapture(endEvent.pointerId);
        }

        target.removeEventListener('pointermove', dragged);
        target.removeEventListener('pointerup', stoppedDragging);
        target.removeEventListener('pointercancel', stoppedDragging);
      };

      target.addEventListener('pointermove', dragged);
      target.addEventListener('pointerup', stoppedDragging);
      target.addEventListener('pointercancel', stoppedDragging);
    },
    [editor, shapeId],
  );
