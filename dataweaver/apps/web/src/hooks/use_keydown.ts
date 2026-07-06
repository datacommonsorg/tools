import { type RefObject, useEffect } from 'react';

type Target = EventTarget | RefObject<EventTarget | null> | null;

type Callback = (event: KeyboardEvent) => void;

interface Config {
  /**
   * This can be used to conditionally enable / disable the event listener.
   *
   * @default true
   */
  isEnabled?: boolean;

  /**
   * A specify dom node or ref you want to attach the event listener to.
   * Defaults to `window`.
   */
  target?: Target;
}

type EventHandler = (event: Event) => void;

interface Listener {
  keyCode: string | string[];
  callback: Callback;
}

interface Query {
  eventHandler: EventHandler;
  listeners: Set<Listener>;
}

const QUERIES = new Map<EventTarget, Query>();

const getEventTargetFromTarget = (target?: Target) => {
  return (target && 'current' in target ? target.current : target) || window;
};

const addListener = (
  eventTarget: EventTarget,
  listeners: Listener,
  eventHandler: EventHandler,
) => {
  const query = QUERIES.get(eventTarget);

  // If query doesn't exist, create new query
  if (!query) {
    QUERIES.set(eventTarget, { eventHandler, listeners: new Set([listeners]) });

    // Note: We need to use capture phase here to ensure that we can catch the
    // event before it's stopped by any other event listener - especially tldraw
    eventTarget.addEventListener('keydown', eventHandler, true);
    return;
  }

  // Else, add this listener to existing set of listeners
  query.listeners.add(listeners);
};

const removeListener = (eventTarget: EventTarget, listener: Listener) => {
  const query = QUERIES.get(eventTarget);
  if (!query) return;

  const { eventHandler, listeners } = query;

  // Remove this listener from existing set of listeners
  listeners.delete(listener);

  // If there are no more listeners, remove the event listener
  if (listeners.size === 0) {
    QUERIES.delete(eventTarget);
    eventTarget.removeEventListener('keydown', eventHandler, true);
  }
};

const emitCallbacks = (eventTarget: EventTarget, event: KeyboardEvent) => {
  const query = QUERIES.get(eventTarget);
  if (!query) return;

  for (const listener of query.listeners) {
    const { keyCode, callback } = listener;

    // If the event code matches the target key code, invoke the callback
    if (
      Array.isArray(keyCode)
        ? keyCode.includes(event.code)
        : event.code === keyCode
    ) {
      callback(event);
    }
  }
};

/**
 * Hook for listening to window `keydown` events. Under the hood, it creates
 * only a single event listener for each target and manages multiple key
 * listeners for improved performance.
 *
 * @param keyCode - The target key [code](https://developer.mozilla.org/en-US/docs/Web/API/KeyboardEvent/code) to listen for. Can also be an array of key codes.
 * @param callback - The callback to invoke when window `keydown` event is fired and the target key is pressed.
 * @param config - Optional configuration object.
 * @param config.isEnabled - Lets you specify whether to listen for events or not. Defaults to `true`.
 * @param config.target - Lets you specify a dom node or ref you want to attach the event listener to. Defaults to `window`.
 *
 * @example
 * useKeydown("KeyA", (event) => console.info(event));
 *
 * @example
 * useKeydown("KeyG", (event) => {
 *   if (event.ctrlKey) console.info("Ctrl + G Pressed!");
 * });
 *
 * @example
 * useKeydown(["ArrowLeft", "ArrowRight"], () => console.info("ArrowLeft or ArrowRight Pressed!"));
 *
 * @example
 * const fooRef = useRef<HTMLDivElement>(null);
 * useKeydown("Escape", () => {}, { target: fooRef });
 */
export const useKeydown = (
  keyCode: string | string[],
  callback: Callback,
  config: Config = {},
) => {
  useEffect(() => {
    if (config.isEnabled ?? true) {
      const eventTarget = getEventTargetFromTarget(config.target);

      const eventHandler = (event: Event) => {
        if ('code' in event) emitCallbacks(eventTarget, event as KeyboardEvent);
      };

      const listener: Listener = { keyCode, callback };
      addListener(eventTarget, listener, eventHandler);
      return () => removeListener(eventTarget, listener);
    }
  }, [config.isEnabled, config.target, keyCode, callback]);
};
