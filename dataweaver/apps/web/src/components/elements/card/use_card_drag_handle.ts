import { useCallback } from 'react';
import { type TLShapeId, useEditor } from 'tldraw';
import { useShapeDragHandle } from '~/hooks/use_shape_drag_handle';

/** Returns {@link useShapeDragHandle} configured to drag card. */
export const useCardDragHandle = (shapeId: TLShapeId) => {
  const editor = useEditor();

  const selectAndReturnSelection = useCallback(() => {
    editor.select(shapeId);
    return [shapeId];
  }, [editor, shapeId]);

  return useShapeDragHandle(selectAndReturnSelection, 'drag-card');
};
