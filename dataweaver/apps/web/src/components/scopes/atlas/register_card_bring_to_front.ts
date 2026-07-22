import type { Editor } from 'tldraw';

/**
 * Move a dragged card to top: this triggers whenever the user moves a card — by
 * any of the ways to drag one (tldraw's native ways or our own drag handlers
 * i.e. on action bars.
 */
export const registerCardBringToFront = (editor: Editor): (() => void) => {
  return editor.sideEffects.registerAfterChangeHandler(
    'shape',
    (previous, next, source) => {
      if (
        // Ignore non-card shapes
        previous.type !== 'card' ||
        next.type !== 'card' ||
        // Or changes that didn't come from the local user
        source !== 'user' ||
        // Or changes that don't move the card
        (previous.x === next.x && previous.y === next.y) ||
        // Or resizes (a move shifts x/y but never w/h)
        previous.props.w !== next.props.w ||
        previous.props.h !== next.props.h
      ) {
        return;
      }

      // Get all selected IDs so that if the user is moving multiple cards, we
      // bring them all to front together
      const selectedIds = editor.getSelectedShapeIds();
      const ids = selectedIds.includes(next.id) ? selectedIds : [next.id];
      editor.bringToFront(ids);
    },
  );
};
