import type { Editor, TLShapeId } from 'tldraw';
import { TABBABLE_ELEMENTS } from '~/hooks/use_focus_trap';
import { CARD_DATA_ATTRIBUTE } from './shapes/card';

const CARD_SELECTOR = `[${CARD_DATA_ATTRIBUTE}]`;

interface CardFocusable {
  element: HTMLElement;
  shapeId: TLShapeId;
}

/**
 * Get every card's focusables list, flattened in reading order
 * (top-to-bottom, left-to-right).
 */
const getCardFocusables = (editor: Editor): CardFocusable[] => {
  const container = editor.getContainer();
  const culledShapes = editor.getCulledShapes();

  return (
    editor
      .getCurrentPageShapes()

      // Current page shapes returns all shapes, including culled ones. So
      // filter those out before proceeding
      .filter((shape) => shape.type === 'card' && !culledShapes.has(shape.id))
      .map((shape) => ({ shape, bounds: editor.getShapePageBounds(shape.id) }))

      // Sort by page bounds (top-to-bottom, left-to-right) so we tab in order
      // of appearance rather than draw order
      .sort((a, b) =>
        a.bounds && b.bounds
          ? a.bounds.y - b.bounds.y || a.bounds.x - b.bounds.x
          : 0,
      )

      // For each card, find its element and read the tabbable elements inside
      .flatMap(({ shape }) => {
        const shapeElement = container.querySelector<HTMLElement>(
          `[data-shape-id='${shape.id}']`,
        );

        // Ignore if we couldn't find the card's wrapper element
        if (!shapeElement) return [];

        // Return every tabbable element inside the card paired with the ID
        const focusableElements =
          shapeElement.querySelectorAll<HTMLElement>(TABBABLE_ELEMENTS);
        return Array.from(focusableElements, (element) => ({
          element,
          shapeId: shape.id,
        }));
      })
  );
};

/** Where a tab press should land next within the list of cards. */
const getTargetIndex = (
  focusables: CardFocusable[],
  activeElement: HTMLElement,
  pressedShiftKey: boolean,
  selectedId: TLShapeId | null,
): number => {
  // Where the focused element sits in the list (-1 when focus is on the canvas
  // rather than on a card focusable)
  const currentIndex = focusables.findIndex(
    (focusable) => focusable.element === activeElement,
  );

  // Already on a focusable: step to the next / previous one, wrapping at ends
  if (currentIndex !== -1) {
    const step = pressedShiftKey ? -1 : 1;
    return (currentIndex + step + focusables.length) % focusables.length;
  }

  // Entering from the canvas with a card selected: dive into that card's first
  // focusable, so tab enters whichever card you just clicked
  if (selectedId) {
    const selectedCardIndex = focusables.findIndex(
      (focusable) => focusable.shapeId === selectedId,
    );
    if (selectedCardIndex !== -1) return selectedCardIndex;
  }

  // Nothing selected: start at the first focusable (tab) or last (shift+tab)
  return pressedShiftKey ? focusables.length - 1 : 0;
};

/**
 * Lets tab / shift+tab reach the focusable content inside cards.
 *
 * Tab steps through a flat ring of every card's focusables (action bar then
 * content, in document order), crossing card boundaries seamlessly and wrapping
 * at the ends. It never selects a card or stops on the card as a whole — only on
 * the focusables within it. (The action bar is hidden until the card is selected
 * or focused; CSS reveals it on `:focus-within` so it can be tabbed to.)
 *
 * We do this ourselves because tldraw swallows Tab to cycle shape selection (see
 * its `useDocumentEvents` handler). Listening in the capture phase lets us run
 * before tldraw's container handler; `markEventAsHandled` then makes tldraw skip
 * the event.
 *
 * @returns A cleanup function that removes the listener.
 */
export const registerCardTabNavigation = (editor: Editor) => {
  const container = editor.getContainer();

  const pressedKey = (event: KeyboardEvent) => {
    // Ignore non-tab keys and modifier combos (alt+tab, ctrl+tab, etc).
    if (event.key !== 'Tab' || event.altKey || event.ctrlKey || event.metaKey) {
      return;
    }

    // Leave tldraw's own text editing alone
    if (editor.getEditingShapeId()) return;

    // A dialog / menu runs its own focus trap — stay out of its way
    if (container.querySelector('dialog[open]')) return;

    // Ignore if the active element isn't an HTMLElement
    const { activeElement } = document;
    if (!(activeElement instanceof HTMLElement)) return;

    // Only handle tab events from the canvas itself (e.g. right after clicking
    // a card to select it) or from inside a card
    if (activeElement !== container && !activeElement.closest(CARD_SELECTOR)) {
      return;
    }

    const focusables = getCardFocusables(editor);
    if (focusables.length === 0) return;

    const targetIndex = getTargetIndex(
      focusables,
      activeElement,
      event.shiftKey,
      editor.getOnlySelectedShapeId(),
    );

    // If we couldn't find a target - ignore rest
    const target = focusables[targetIndex];
    if (!target) return;

    // Take over from tldraw's shape-cycling and the browser's native tab order
    event.preventDefault();
    editor.markEventAsHandled(event);
    target.element.focus();
  };

  container.addEventListener('keydown', pressedKey, { capture: true });
  return () => {
    container.removeEventListener('keydown', pressedKey, { capture: true });
  };
};
