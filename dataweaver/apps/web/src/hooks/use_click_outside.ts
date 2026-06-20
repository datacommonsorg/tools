import type { RefObject } from 'react';
import { useEffect } from 'react';

type Callback = (event: Event) => void;

interface Config {
  /**
   * Whether or not to listen to click outside events.
   *
   * @default true
   */
  isEnabled?: boolean;

  /**
   * CSS selectors for elements that should not count as 'outside'. A click on
   * any element matching (or descending from) one of these is ignored.
   */
  ignoreTargets?: string[];
}

/** Small hook to detect an outside click on a given `targetRef`. */
export const useClickOutside = <TElement extends HTMLElement>(
  targetRef: RefObject<TElement | null>,
  callback: Callback,
  config: Config = {},
) => {
  useEffect(() => {
    if ((config.isEnabled ?? true) && targetRef.current) {
      const target = targetRef.current;

      const clickedOutside = (event: MouseEvent) => {
        const element = event.target;
        if (!(element instanceof HTMLElement) || target.contains(element)) {
          return;
        }

        // Skip clicks that land on an opted-out target
        if (
          config.ignoreTargets &&
          config.ignoreTargets.some((selector) => element.closest(selector))
        ) {
          return;
        }

        callback(event);
      };

      document.addEventListener('mousedown', clickedOutside, { passive: true });
      return () => document.removeEventListener('mousedown', clickedOutside);
    }
  }, [targetRef, callback, config?.isEnabled, config.ignoreTargets]);
};
