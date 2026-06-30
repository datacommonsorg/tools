import { type TLShape, useValue } from 'tldraw';
import { useAtlas } from '~/components/scopes/atlas/atlas_provider';

export interface SelectedCard {
  /** The card's tldraw shape id. */
  id: string;

  /** The card's display title. */
  title: string;
}

/**
 * Reactively read the cards currently selected on the canvas. Updates as the
 * selection changes, and is safe to call from outside the tldraw component
 * tree (it reads the editor exposed via `useAtlas`).
 */
export const useAtlasSelectedCards = (): SelectedCard[] => {
  const { editor } = useAtlas();

  return useValue('atlas-selected-cards', () => {
    if (!editor) return [];

    return editor.getSelectedShapeIds().reduce<SelectedCard[]>((cards, id) => {
      const shape = editor.getShape<TLShape<'card'>>(id);

      // Ignore if the shape is not a card or has no title for whatever reason
      if (!shape || shape.type !== 'card' || !shape.props.title) return cards;

      cards.push({ id, title: shape.props.title });
      return cards;
    }, []);
  }, [editor]);
};
