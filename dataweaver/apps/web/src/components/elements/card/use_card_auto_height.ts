import { useIsomorphicLayoutEffect } from 'motion/react';
import { type RefObject, useRef } from 'react';
import { type TLShapeId, useEditor } from 'tldraw';

/** Sub-pixel tolerance, in px, to absorb rounding and avoid feedback loops. */
const EPSILON = 1;

/**
 * Keeps a card shape's `h` prop equal to its rendered content height, capped at
 * `maxHeight`. Uses given ref whose *natural* (uncapped) height should drive
 * the card — its `scrollHeight` is read, so the element may itself be clamped
 * and scrollable without throwing the measurement off.
 *
 * Because the shape's geometry (and therefore its hit area and the auto
 * placement footprint) is derived from `h`, syncing `h` to the content makes
 * clicking the empty space below a short card no longer select it, and makes
 * the next card stack just below the real card height.
 */
export const useCardAutoHeight = <TElement extends HTMLElement>(
  containerRef: RefObject<TElement | null>,
  shapeId: TLShapeId,
  maxHeight: number,
) => {
  const editor = useEditor();

  const lastHeightRef = useRef<number | null>(null);

  useIsomorphicLayoutEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const sync = () => {
      // tldraw culls off-screen shapes with 'display: none', which collapses
      // the element to 0 and fires the observer. Ignore those measurements so
      // we never write 'h = 0'
      if (container.offsetParent === null || container.scrollHeight === 0) {
        return;
      }

      // 'scrollHeight' reports the natural content height even while the
      // element is clamped by 'max-height'; it excludes borders, so include it
      const bordersHeight = container.offsetHeight - container.clientHeight;
      const contentHeight = container.scrollHeight + bordersHeight;
      const newHeight = Math.round(Math.min(contentHeight, maxHeight));

      // Avoid feedback loops: If the new height is within distance of the last
      if (
        lastHeightRef.current !== null &&
        Math.abs(newHeight - lastHeightRef.current) < EPSILON
      ) {
        return;
      }

      const shape = editor.getShape(shapeId);

      // Ignore if the shape is isn't found or not a card
      if (!shape || shape.type !== 'card') return;

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
    const observer = new ResizeObserver(sync);
    observer.observe(container);
    return () => observer.disconnect();
  }, [editor, shapeId, maxHeight]);
};
