import { useCallback } from 'react';
import { useEditor } from 'tldraw';
import { useShapeDragHandle } from '~/hooks/use_shape_drag_handle';

/** Returns {@link useShapeDragHandle} configured to drag the whole selection. */
export const useSelectionDragHandle = () => {
  const editor = useEditor();

  const getSelectionShapeIds = useCallback(() => {
    return editor.getSelectedShapeIds();
  }, [editor]);

  return useShapeDragHandle(getSelectionShapeIds, 'drag-selection');
};
