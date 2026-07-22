import { useCallback, useRef } from 'react';
import { useEditor, useQuickReactor, useValue } from 'tldraw';

/** Screen-space margin the selection box extends past the cards, in pixels. */
const INSET_SIDES_AND_BOTTOM = 16;

/** Larger top margin, leaving room to seat the action panel above the cards. */
const INSET_TOP = 60;

/**
 * Tracks the multi-selection box: whether it should show (more than one shape
 * selected) and where. Returns a ref callback that seats the box over the
 * selection and keeps it there as the canvas pans/zooms.
 */
export const useSelectionPosition = () => {
  const editor = useEditor();
  const containerRef = useRef<HTMLDivElement>(null);

  const hasMultipleSelected = useValue(
    'multi-selection-active',
    () => editor.getSelectedShapeIds().length > 1,
    [editor],
  );

  const position = useCallback(() => {
    const bounds = editor.getSelectionPageBounds();
    const { z: zoom } = editor.getCamera();

    const container = containerRef.current;
    if (!container || !bounds) return;

    const origin = editor.pageToViewport({ x: bounds.x, y: bounds.y });
    const left = origin.x - INSET_SIDES_AND_BOTTOM;
    const top = origin.y - INSET_TOP;
    const width = bounds.width * zoom + INSET_SIDES_AND_BOTTOM * 2;
    const height = bounds.height * zoom + INSET_TOP + INSET_SIDES_AND_BOTTOM;

    container.style.transform = `translate(${left}px, ${top}px)`;
    container.style.width = `${width}px`;
    container.style.height = `${height}px`;
  }, [editor]);

  // Keep the box tracking the canvas while it's mounted
  useQuickReactor('position multi-selection', position, [position]);

  // On mount; set container + position to ensure it's always correctly placed.
  const setContainer = useCallback(
    (container: HTMLDivElement | null) => {
      containerRef.current = container;
      position();
    },
    [position],
  );

  return { hasMultipleSelected, setContainer };
};
