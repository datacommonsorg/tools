import { type RefObject, useEffect } from 'react';

/**
 * Focuses `ref`'s element whenever `isEnabled` becomes true.
 */
export const useAutoFocus = <TElement extends HTMLElement>(
  ref: RefObject<TElement | null>,
  isEnabled = true,
) => {
  // biome-ignore lint/correctness/useExhaustiveDependencies: ref is stable
  useEffect(() => {
    if (isEnabled) ref.current?.focus();
  }, [isEnabled]);
};
