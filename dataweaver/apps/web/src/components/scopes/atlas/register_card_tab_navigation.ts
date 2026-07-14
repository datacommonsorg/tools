import { type Editor, react, type TLShapeId } from 'tldraw';
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
      // of appearance rather than draw order. Shapes without bounds sink to the
      // end, so the comparator stays a strict weak ordering
      .sort((a, b) => {
        if (!a.bounds && !b.bounds) return 0;
        if (!a.bounds) return 1;
        if (!b.bounds) return -1;
        return a.bounds.y - b.bounds.y || a.bounds.x - b.bounds.x;
      })

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

  // Entering from the canvas with a card selected: dive into that card — its
  // first focusable when tabbing forward, its last when tabbing backward — so
  // tab enters whichever card you just clicked
  if (selectedId) {
    const shapeIds = focusables.map((focusable) => focusable.shapeId);
    const selectedCardIndex = pressedShiftKey
      ? shapeIds.lastIndexOf(selectedId)
      : shapeIds.indexOf(selectedId);
    if (selectedCardIndex !== -1) return selectedCardIndex;
  }

  // Nothing selected: start at the first focusable (tab) or last (shift+tab)
  return pressedShiftKey ? focusables.length - 1 : 0;
};

/**
 * Enable tab / shift+tab to reach the focusable content inside cards. Under the
 * hood we listen for tab presses and override tldraw's own shape-cycling
 * behavior to instead cycle through the focusable elements inside cards in
 * reading order (top-to-bottom, left-to-right). This allows users to tab into a
 * card's content and then tab out of it to the next card seamlessly.
 */
export const registerCardTabNavigation = (editor: Editor) => {
  const container = editor.getContainer();

  // The focusables list only changes when the canvas does, so cache it between
  // tab presses instead of rebuilding it on every keydown
  let cachedFocusables: CardFocusable[] | null = null;

  // Track the exact store state the list derives from: the current page's
  // shape records (existence, position, size — anything affecting reading
  // order) and the culled set. This effect only runs if those change and not
  // if the store changes in ways that don't affect the list (e.g. hover,
  // pointer, camera pans etc.
  const cleanupStoreReactor = react('invalidate card focusables cache', () => {
    editor.getCurrentPageShapes();
    editor.getCulledShapes();
    cachedFocusables = null;
  });

  // DOM changes cover card content re-rendering without a store change. Only
  // mutations inside a card can affect the list
  const observer = new MutationObserver((mutations) => {
    const touchesCard = mutations.some(
      (mutation) =>
        mutation.target instanceof HTMLElement &&
        mutation.target.closest(CARD_SELECTOR),
    );
    if (touchesCard) cachedFocusables = null;
  });
  observer.observe(container, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ['tabindex', 'disabled', 'href', 'type'],
  });

  const pressedKey = (event: KeyboardEvent) => {
    // Ignore non-tab keys and modifier combos (alt+tab, ctrl+tab, etc).
    if (event.key !== 'Tab' || event.altKey || event.ctrlKey || event.metaKey) {
      return;
    }

    // Leave tldraw's own text editing alone
    if (editor.getEditingShapeId()) return;

    // Ignore if the active element isn't an HTMLElement
    const { activeElement } = document;
    if (!(activeElement instanceof HTMLElement)) return;

    // A dialog / menu runs its own focus trap — stay out of its way. Covers the
    // native <dialog> plus ARIA widgets (menu, listbox, dialog) whose own
    // keyboard handling we'd otherwise clobber from the capture phase
    if (
      container.querySelector('dialog[open]') ||
      activeElement.closest('[role="dialog"], [role="menu"], [role="listbox"]')
    ) {
      return;
    }

    // Only handle tab events from the canvas itself (e.g. right after clicking
    // a card to select it) or from inside a card
    if (activeElement !== container && !activeElement.closest(CARD_SELECTOR)) {
      return;
    }

    // Build the focusables list if we don't have a cached one yet
    cachedFocusables ??= getCardFocusables(editor);
    const focusables = cachedFocusables;
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
    observer.disconnect();
    cleanupStoreReactor();
  };
};
