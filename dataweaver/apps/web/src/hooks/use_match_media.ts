import { useIsomorphicLayoutEffect } from 'motion/react';
import { useCallback, useState } from 'react';
import {
  getMatchMediaQuery,
  type MatchMediaKey,
} from '~/functions/match_media';

interface Config {
  /**
   * Fallback value that is returned in SSR and first match of any unique query.
   *
   * @default false
   */
  defaultValue?: boolean | null;

  /**
   * Whether or not to listen to events.
   *
   * @default true
   */
  isEnabled?: boolean;
}

type EventHandler = (event: MediaQueryListEvent) => void;

interface Query {
  matchMedia: MediaQueryList;
  existingListeners: EventHandler[];
  eventHandler: EventHandler;
}

const QUERIES = new Map<string, Query>();

/**
 * Stateful hook that uses the matchMedia API.
 *
 * @param queryKey - The query key to match for.
 * @param config - _Optional_ configuration object.
 * @param config.defaultValue - _Optional_ fallback value that is returned in
 * SSR and first match of any unique query. Defaults to `false`.
 * @param config.isEnabled - _Optional_ whether or not to listen to events.
 * Defaults to `true`.
 * @param config.layoutEffect - _Optional_ whether or not to use
 * `useLayoutEffect` instead of `useEffect` on client. Defaults to `false`.
 *
 * @example
 * useMatchMedia("(pointer: coarse)") -> Checks if the browser matches coarse;
 * device of limited accuracy (touch).
 *
 * @example useMatchMedia("(min-width: 600px)") -> Checks if the browser
 * matches a minimum width of 600px.
 *
 * @returns matches - `true` / `false` if the device matches the query, or
 * `defaultValue` as fallback.
 */
export const useMatchMedia = <
  TConfig extends Config = Config,
  TDefaultValue extends
    | TConfig['defaultValue']
    | never = TConfig['defaultValue'] extends undefined
    ? undefined
    : TConfig['defaultValue'] extends null
      ? null
      : never,
>(
  queryKey: MatchMediaKey,
  config: Partial<TConfig> = {},
) => {
  const query = getMatchMediaQuery(queryKey);

  const getExistingMatch = useCallback(() => {
    const matchedQuery = QUERIES.get(query);

    // If query already exists, return its matched value
    if (matchedQuery) return matchedQuery.matchMedia.matches;

    // Else, return config default value if it exists or fallback (false)
    return config.defaultValue === undefined ? false : config.defaultValue;
  }, [config.defaultValue, query]);

  const createEventHandler = useCallback(
    (query: string) => (event: MediaQueryListEvent) => {
      const matchedQuery = QUERIES.get(query);

      if (matchedQuery) {
        matchedQuery.existingListeners.forEach((listener) => {
          listener(event);
        });
      }
    },
    [],
  );

  const addListener = useCallback(
    (query: string, listener: EventHandler) => {
      const matchedQuery = QUERIES.get(query);

      // If query already exists, add this new listener to existing array
      if (matchedQuery) {
        matchedQuery.existingListeners.push(listener);
        return matchedQuery.matchMedia.matches;
      }

      // Else, first query, so create it...
      const newQuery = {
        matchMedia: window.matchMedia(query),
        existingListeners: [listener],
        eventHandler: createEventHandler(query),
      };
      QUERIES.set(query, newQuery);

      // Listen to changes with fallback
      const currentMatchMedia = newQuery.matchMedia;
      if (!currentMatchMedia.addEventListener) {
        currentMatchMedia.addListener(newQuery.eventHandler);
      } else {
        currentMatchMedia.addEventListener('change', newQuery.eventHandler);
      }

      return newQuery.matchMedia.matches;
    },
    [createEventHandler],
  );

  const removeListener = useCallback(
    (query: string, listener: EventHandler) => {
      const matchedQuery = QUERIES.get(query);

      // If this matches, filter out this listener from existing array
      if (matchedQuery) {
        matchedQuery.existingListeners = matchedQuery.existingListeners.filter(
          (l) => l !== listener,
        );
      }

      // Ignore unsubscribe below if theres any more existing listeners
      if (!matchedQuery || matchedQuery.existingListeners.length > 0) return;

      // Unsubscribe from changes with fallback
      const currentMatchMedia = matchedQuery.matchMedia;
      if (!currentMatchMedia.removeEventListener) {
        currentMatchMedia.removeListener(matchedQuery.eventHandler);
      } else {
        currentMatchMedia.removeEventListener(
          'change',
          matchedQuery.eventHandler,
        );
      }

      QUERIES.delete(query);
    },
    [],
  );

  const [matches, setMatches] = useState<boolean | TDefaultValue>(
    getExistingMatch,
  );

  useIsomorphicLayoutEffect(() => {
    if (config.isEnabled ?? true) {
      const listener = (event: MediaQueryListEvent) => {
        setMatches(event.matches);
      };

      // On mount we only checked if there was an existing match. So here we
      // set matches again in case this is the first of this query
      const matches = addListener(query, listener);
      setMatches(matches);

      return () => removeListener(query, listener);
    }
  }, [config.isEnabled, query, addListener, removeListener]);

  return matches;
};
