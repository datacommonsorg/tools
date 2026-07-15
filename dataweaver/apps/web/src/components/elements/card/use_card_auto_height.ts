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
 *
 * When `enabled` is `false`, syncing is paused — the card keeps its current
 * height. Useful when the visible content (e.g. a table tab) shouldn't drive
 * the card's height.
 */
export const useCardAutoHeight = (
  shapeId: TLShapeId,
  containerRef: RefObject<HTMLElement | null>,
  contentRef: RefObject<HTMLElement | null>,
  maxHeight: number,
  enabled = true,
) => {
  const editor = useEditor();

  const lastHeightRef = useRef<number | null>(null);

  useIsomorphicLayoutEffect(() => {
    const container = containerRef.current;
    const content = contentRef.current;
    if (!container || !content) return;

    // Track whether async content (e.g. Recharts SVG) has been inserted.
    // Until it has, only allow the card to GROW — never shrink — so a
    // freshly-created card doesn't collapse to header-only height before the
    // chart renders.
    let contentSettled = false;

    const sync = () => {
      if (!enabled) return;

      // Skip while the user is actively dragging a resize handle — avoids
      // fighting with tldraw's resize logic. The pending ResizeObserver
      // callback after pointer-up will re-trigger sync once the editor is idle.
      if (editor.isIn('select.resizing')) return;

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

      // Before async content has settled, only allow growing the card so it
      // doesn't shrink to a tiny size while waiting for the chart SVG.
      if (!contentSettled && newHeight < shape.props.h) return;

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
    const resizeObserver = new ResizeObserver(() => {
      contentSettled = true;
      sync();
    });
    resizeObserver.observe(container);

    // --- MutationObserver: catches async child content insertion ---
    // Recharts' ResponsiveContainer (and similar libraries) render chart SVGs
    // asynchronously after measuring their parent width. Once useCardAutoHeight
    // writes a smaller `h`, the container's box is max-height-capped so the
    // ResizeObserver won't fire when new children appear (the box doesn't
    // grow). A MutationObserver detects these insertions and re-measures.
    // Debounced via rAF to avoid layout thrashing from rapid subtree mutations
    // (e.g. tooltips appearing/disappearing on hover).
    let mutationFrameId: number | null = null;
    const syncOnMutation = () => {
      if (mutationFrameId !== null) return;
      mutationFrameId = requestAnimationFrame(() => {
        mutationFrameId = null;
        contentSettled = true;
        sync();
      });
    };
    const mutationObserver = new MutationObserver(syncOnMutation);
    mutationObserver.observe(container, { childList: true, subtree: true });

    return () => {
      resizeObserver.disconnect();
      mutationObserver.disconnect();
      if (mutationFrameId !== null) cancelAnimationFrame(mutationFrameId);
    };
  }, [editor, shapeId, maxHeight, enabled]);
};
