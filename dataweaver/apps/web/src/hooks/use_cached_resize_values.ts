import { useEffect, useRef } from 'react';
import { Resize } from '~/utilities/resize';

/**
 * Hook to cache values that depend on window resize.
 *
 * The key assumption is that cached values will not change unless the window
 * size has changed, allowing for performance optimization by avoiding expensive
 * recalculations.
 *
 * Under the hood we only attach a single resize listener no matter how many
 * elements are using this hook for improved performance.
 *
 * @param callback A callback function that computes values to cache.
 * @returns A getter where the first argument is an optional `invalidate`
 * boolean. Pass `true` to force re-computation regardless of resize state. If
 * additional arguments are passed they are forwarded as second value onwards.
 */
export function useCachedResizeValues<
  TCallbackArgs extends unknown[],
  TCallbackReturn,
>(
  callback: (...args: TCallbackArgs) => TCallbackReturn,
): (invalidate?: boolean, ...args: TCallbackArgs) => TCallbackReturn {
  const cachedValueRef = useRef<TCallbackReturn>(undefined);
  const resizeRef = useRef<Resize>(null);

  useEffect(() => {
    return () => {
      if (resizeRef.current) {
        resizeRef.current.cleanup();
        resizeRef.current = null;
      }
    };
  }, []);

  return (invalidate = false, ...args: TCallbackArgs): TCallbackReturn => {
    // Initialize resize instance if not already done
    if (!resizeRef.current) resizeRef.current = new Resize();

    // If we have a cached value and neither a resize nor an explicit invalidation
    // has occurred since it was cached, return it as is
    if (
      cachedValueRef.current !== undefined &&
      !resizeRef.current.resized &&
      !invalidate
    ) {
      return cachedValueRef.current;
    }

    // Otherwise; recompute and cache, clearing the resize dirty flag
    resizeRef.current.clear();
    const result = callback(...args);
    cachedValueRef.current = result;
    return result;
  };
}
