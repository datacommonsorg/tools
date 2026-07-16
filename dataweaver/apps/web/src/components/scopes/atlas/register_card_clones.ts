import type { Editor, TLShapeId } from 'tldraw';
import type { CardShape } from './helpers';

export interface CardClones {
  /**
   * Mirror a streamed content update from an origin card to its tracked
   * clones. Once the origin resolves (`isLoading: false`) the clones are
   * released and follow no further updates.
   */
  mirrorUpdate(originId: TLShapeId, props: Partial<CardShape['props']>): void;

  /** Unregister the side effects and drop clone tracking. */
  cleanup(): void;
}

/**
 * Track clones of still-loading cards (copy/paste, duplicate) so they behave
 * like their origin until its content arrives:
 *
 * - A clone created while its origin is still loading copies the origin's
 *   props and is tracked, so content streamed to the origin mirrors to it
 *   (the provider calls `mirrorUpdate` as updates arrive).
 * - Deleting a still-loading origin deletes its clones too — they would
 *   never resolve into real content.
 *
 * Clones are recognized by `meta.originId`: cards created through the `add`
 * flow stamp their own id, so anything whose `originId` differs was cloned
 * from an existing card.
 */
export const registerCardClones = (editor: Editor): CardClones => {
  const tracked = new Map<TLShapeId, Set<TLShapeId>>();

  // A clone of a still-loading origin starts as a copy of the origin's
  // current props and is tracked from creation
  const cleanupMirrorCreated = editor.sideEffects.registerBeforeCreateHandler(
    'shape',
    (shape) => {
      const originId = shape.meta.originId as TLShapeId | undefined;
      if (shape.type !== 'card' || originId === shape.id) return shape;

      const originShape =
        shape.props.isLoading && originId
          ? editor.getShape(originId)
          : undefined;
      if (!originShape || originShape.type !== 'card') return shape;

      const clones = tracked.get(originShape.id) ?? new Set<TLShapeId>();
      clones.add(shape.id);
      tracked.set(originShape.id, clones);

      return { ...shape, props: { ...originShape.props } };
    },
  );

  // If a still-loading origin is deleted, its clones go with it
  const cleanupCascadeDeleted = editor.sideEffects.registerAfterDeleteHandler(
    'shape',
    (shape) => {
      if (shape.type !== 'card') return;

      const clones = tracked.get(shape.id);
      if (!clones) return;

      for (const cloneId of clones) {
        if (editor.getShape(cloneId)) editor.deleteShapes([cloneId]);
      }

      tracked.delete(shape.id);
    },
  );

  return {
    mirrorUpdate(originId, props) {
      const clones = tracked.get(originId);
      if (!clones) return;

      for (const cloneId of clones) {
        if (editor.getShape(cloneId)) {
          editor.updateShape({ id: cloneId, type: 'card', props });
        }
      }

      // Once resolved, no further updates arrive so stop following
      if (props.isLoading === false) tracked.delete(originId);
    },
    cleanup() {
      cleanupMirrorCreated();
      cleanupCascadeDeleted();
      tracked.clear();
    },
  };
};
