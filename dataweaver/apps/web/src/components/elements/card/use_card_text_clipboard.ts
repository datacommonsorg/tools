import { type RefObject, useEffect } from 'react';

/**
 * Lets the user copy/cut highlighted text out of a card.
 *
 * TLDraw registers `copy` / `cut` listeners on the container document and,
 * while a shape is selected, calls `preventDefault` to copy that *shape* — so
 * the browser never copies text the user highlighted inside a card.
 *
 * We intercept the same events in the capture phase (which runs before
 * TLDraw's bubble-phase listeners) and, when the current selection lives inside
 * this card, call `stopPropagation` so TLDraw's handler never runs. We
 * deliberately do not `preventDefault`, so the browser still performs its
 * native text copy. When there is no selection inside the card the event is
 * left untouched, preserving TLDraw's shape copy/cut behaviour.
 */
export const useCardTextClipboard = <TElement extends HTMLElement>(
  containerRef: RefObject<TElement | null>,
) => {
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const document = container.ownerDocument;

    const copied = (event: ClipboardEvent) => {
      const selection = document.getSelection();
      const isTextSelectedInCard =
        selection &&
        !selection.isCollapsed &&
        selection.anchorNode &&
        container.contains(selection.anchorNode);

      // If text selection is inside card - prevent TLDraw from hijacking the
      // event - keep native copy / cut behavior
      if (isTextSelectedInCard) event.stopPropagation();
    };

    document.addEventListener('copy', copied, true);
    document.addEventListener('cut', copied, true);

    return () => {
      document.removeEventListener('copy', copied, true);
      document.removeEventListener('cut', copied, true);
    };
  }, [containerRef]);
};
