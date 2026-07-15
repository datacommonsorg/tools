import { type RefObject, useEffect, useRef } from 'react';

/**
 * Hook to cache values that depend on an element's size.
 *
 * The key assumption is that cached values will not change unless the observed
 * element has resized, allowing for performance optimization by avoiding
 * expensive recalculations. A resize only marks the cache stale; the value is
 * not recomputed until the getter is next called.
 */
export function useCachedResizeValues<
  TCallbackArgs extends unknown[],
  TCallbackReturn,
>(
  observedElementRef: RefObject<HTMLElement | null>,
  callback: (...args: TCallbackArgs) => TCallbackReturn,
): (...args: TCallbackArgs) => TCallbackReturn {
  const cachedValueRef = useRef<TCallbackReturn>(undefined);
  const resizedRef = useRef(false);

  useEffect(() => {
    const observedElement = observedElementRef.current;
    if (!observedElement) return;

    const observer = new ResizeObserver(() => {
      // Mark the cache as dirty on resize - forcing the next call to recompute
      resizedRef.current = true;
    });
    observer.observe(observedElement);
    return () => observer.disconnect();
  }, [observedElementRef]);

  return (...args: TCallbackArgs): TCallbackReturn => {
    // If we have a cached value and no resize has occurred since it was
    // cached, return it as is
    if (cachedValueRef.current !== undefined && !resizedRef.current) {
      return cachedValueRef.current;
    }

    // Otherwise; recompute and cache, clearing the resize dirty flag
    resizedRef.current = false;
    const result = callback(...args);
    cachedValueRef.current = result;
    return result;
  };
}
