import { useIsomorphicLayoutEffect } from 'motion/react';
import { type RefObject, useRef } from 'react';
import { type TLShapeId, useEditor } from 'tldraw';

/** Sub-pixel tolerance, in px, to absorb rounding and avoid feedback loops. */
const EPSILON = 1;

/**
 * Measures the content height of a card, including any fixed 'chrome' (title
 * bar, padding, etc.) that is outside the scrollable body. The returned value
 * is the total height of the card's content.
 */
const measureContentHeight = (
  container: HTMLElement,
  content: HTMLElement,
): number => {
  const contentParent = content.parentElement;
  if (!contentParent) return content.offsetHeight;

  const chromeAroundContent =
    container.offsetHeight - contentParent.clientHeight;
  return content.offsetHeight + chromeAroundContent;
};

/**
 * Keeps a card shape's `h` prop equal to its rendered content height. After
 * user manually resizes card - syncing stops and the new height is preserved.
 */
export const useCardAutoHeight = (
  shapeId: TLShapeId,
  containerRef: RefObject<HTMLElement | null>,
  contentRef: RefObject<HTMLElement | null>,
  maxHeight: number,
) => {
  const editor = useEditor();

  const lastHeightRef = useRef<number | null>(null);

  useIsomorphicLayoutEffect(() => {
    const container = containerRef.current;
    const content = contentRef.current;
    if (!container || !content) return;

    const sync = () => {
      const shape = editor.getShape(shapeId);

      // Ignore if the shape isn't found or isn't a card
      if (!shape || shape.type !== 'card') return;

      // Only sync if user hasn't manually resized - once they do stop syncing
      // and use the new height as is
      if (shape.props.isManuallyResized) return;

      // tldraw culls off-screen shapes with 'display: none', which collapses
      // the element to 0 and fires the observer. Ignore those measurements so
      // we never write 'h = 0'
      if (container.offsetParent === null || container.scrollHeight === 0) {
        return;
      }

      const contentHeight = measureContentHeight(container, content);
      const newHeight = Math.round(Math.min(contentHeight, maxHeight));

      // Avoid feedback loops: If the new height is within distance of the last
      if (
        lastHeightRef.current !== null &&
        Math.abs(newHeight - lastHeightRef.current) < EPSILON
      ) {
        return;
      }

      lastHeightRef.current = newHeight;

      // Lastly - ignore if new height is already at current shape height
      if (Math.abs(shape.props.h - newHeight) < EPSILON) return;

      // Apply the new height to the shape, but don't record it in history —
      // this is a reactive sync, not a user action so don't pollute stack
      editor.run(
        () => {
          editor.updateShape({
            id: shapeId,
            type: 'card',
            props: { h: newHeight },
          });
        },
        { history: 'ignore' },
      );
    };

    sync();

    // --- ResizeObserver: catches size changes of the container itself ---
    const resizeObserver = new ResizeObserver(sync);
    resizeObserver.observe(container);

    // --- MutationObserver: catches async child content insertion ---
    // Recharts' ResponsiveContainer (and similar libraries) render chart SVGs
    // asynchronously after measuring their parent width. Once useCardAutoHeight
    // writes a smaller `h`, the container's box is max-height-capped so the
    // ResizeObserver won't fire when new children appear (the box doesn't
    // grow). A MutationObserver detects these insertions and re-measures.
    const mutationObserver = new MutationObserver(sync);
    mutationObserver.observe(container, { childList: true, subtree: true });

    return () => {
      resizeObserver.disconnect();
      mutationObserver.disconnect();
    };
  }, [editor, shapeId, maxHeight]);
};
