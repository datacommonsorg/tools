import type { Editor, TLParentId, TLShapeId } from 'tldraw';

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

      // This fires on every drag tick, once per card per frame; so a naive
      // 'bringToFront' would run redundant index math and store writes on
      // each one. Skip it when every group is already at the tail of its
      // parent's sorted children, so 'bringToFront' runs once per drag session
      const idsByParent = new Map<TLParentId, TLShapeId[]>();
      for (const id of ids) {
        const shape = editor.getShape(id);
        if (shape === undefined) continue;
        const group = idsByParent.get(shape.parentId) ?? [];
        group.push(id);
        idsByParent.set(shape.parentId, group);
      }

      let alreadyAtFront = true;
      for (const [parentId, group] of idsByParent) {
        const siblingIds = editor.getSortedChildIdsForParent(parentId);
        const tailIds = siblingIds.slice(-group.length);
        const groupSet = new Set(group);
        if (!tailIds.every((id) => groupSet.has(id))) {
          alreadyAtFront = false;
          break;
        }
      }

      if (alreadyAtFront) return;

      editor.bringToFront(ids);
    },
  );
};
