import type { RefObject } from 'react';
import { type Editor, type TLShapeId, useQuickReactor } from 'tldraw';

/**
 * Clears any text the user highlighted inside a card once it stops being the
 * single (focused) selection — scoped to given `containerRef` so it never
 * wipes a selection elsewhere in the app.
 *
 * Runs synchronously via `useQuickReactor`, before React flips the content's
 * `user-select` to `none`. Clearing it any later can cause selection to 'stick'
 * in the card.
 */
export const useCardClearTextSelection = <TElement extends HTMLElement>(
  containerRef: RefObject<TElement | null>,
  editor: Editor,
  shapeId: TLShapeId,
) => {
  useQuickReactor('clear card text selection on blur', () => {
    // Reads selection reactively, so this re-runs whenever it changes
    const selectedIds = editor.getSelectedShapeIds();
    const isSelectedAndSingleSelection =
      selectedIds.length === 1 && selectedIds[0] === shapeId;
    if (isSelectedAndSingleSelection) return;

    const activeSelection = window.getSelection();
    const container = containerRef.current;

    // Only clear when the selection lives inside 'this' card
    if (
      activeSelection &&
      !activeSelection.isCollapsed &&
      container &&
      activeSelection.anchorNode &&
      container.contains(activeSelection.anchorNode)
    ) {
      activeSelection.removeAllRanges();
    }
  }, [containerRef, editor, shapeId]);
};
