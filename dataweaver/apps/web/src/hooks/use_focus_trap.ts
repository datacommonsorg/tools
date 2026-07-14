import type { RefObject } from 'react';

import { useKeydown } from './use_keydown';

export const TABBABLE_ELEMENTS = [
  "a[href]:not([tabindex='-1'])",
  "button:not([tabindex='-1']):not(:disabled)",
  "input:not([type='hidden']):not([tabindex='-1']):not(:disabled)",
  "select:not([tabindex='-1']):not(:disabled)",
  "textarea:not([tabindex='-1']):not(:disabled)",
  "[tabindex]:not([tabindex='-1'])",
].join(', ');

interface Config {
  /**
   * Whether or not to listen to focus trap events.
   *
   * @default true
   */
  isEnabled?: boolean;

  /**
   * By default this hook will only trap focus of the following elements:
   * - `a[href]:not([tabindex='-1'])`
   * - `button:not([tabindex='-1']):not(:disabled)`
   * - `input:not([tabindex='-1']):not(:disabled)`
   * - `select:not([tabindex='-1']):not(:disabled)`
   * - `textarea:not([tabindex='-1']):not(:disabled)`
   * - `[tabindex='0']`
   *
   * If you want to change the list of focusable elements, you can pass a custom
   * string of elements here.
   *
   * @example
   * "input:not([disabled]), select:not([disabled]), textarea:not([disabled])"
   */
  tabbableElements?: string;
}

/**
 * Hook to add focus trap to a given `ref` or array of `refs`.
 *
 * @param targetRef The ref or array of refs to add the focus trap to.
 * @param config The configuration for the focus trap.
 */
export const useFocusTrap = <TElement extends HTMLElement | null>(
  targetRef: RefObject<TElement> | RefObject<TElement>[],
  config: Config = {},
) => {
  const keepFocusWithinTarget = (event: KeyboardEvent) => {
    // Normalize targetRef to always be an array
    const targets = Array.isArray(targetRef) ? targetRef : [targetRef];

    // Get all valid target elements
    const validTargets = targets
      .map((ref) => ref.current)
      .filter((target): target is NonNullable<TElement> => target !== null);
    if (validTargets.length === 0) return;

    // Get all focusable elements from all valid targets
    const focusableElements = validTargets.flatMap((target) => {
      const elements = target.querySelectorAll<HTMLElement>(
        config.tabbableElements ?? TABBABLE_ELEMENTS,
      );
      return Array.from(elements);
    });

    const firstFocusableElement = focusableElements[0];
    const lastFocusableElement =
      focusableElements[focusableElements.length - 1];

    // If neither exist, just prevent the default behavior. There may just be
    // no focusable elements currently (but there could be in the future)
    if (!firstFocusableElement || !lastFocusableElement) {
      event.preventDefault();
      return;
    }

    // Ignore if active element isn't a HTMLElement
    const { activeElement } = document;
    if (!(activeElement instanceof HTMLElement)) return;

    // Check if active element is within any target and if it's not, focus
    // respective first or last focusable element
    if (!validTargets.some((target) => target.contains(activeElement))) {
      // The element wasn't in the focus trap, so focus the next element
      // relative to the direction of the tab key
      const targetElement = event.shiftKey
        ? lastFocusableElement
        : firstFocusableElement;
      targetElement.focus();
      event.preventDefault();
      return;
    }

    // If we reach the last focusable element, loop back to the first one
    if (!event.shiftKey && activeElement === lastFocusableElement) {
      firstFocusableElement.focus();
      event.preventDefault();
      return;
    }

    // If we reach the first focusable element, loop back to the last one
    if (event.shiftKey && activeElement === firstFocusableElement) {
      lastFocusableElement.focus();
      event.preventDefault();
      return;
    }

    // If we got here, the active element is within the focus trap and not at
    // the edges - so we don't need to do anything
  };

  useKeydown('Tab', keepFocusWithinTarget, {
    isEnabled: config.isEnabled,

    // Listen during the capture phase so the trap intercepts `Tab` before a
    // focused descendant (e.g. tldraw's canvas) can consume it
    capture: true,
  });
};
