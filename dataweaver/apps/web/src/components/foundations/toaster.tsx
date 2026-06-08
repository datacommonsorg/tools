'use client';

import { EASE_OUT } from '@package/tokens/ts';
import { AnimatePresence, m } from 'motion/react';
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
} from 'react';
import { useMatchMedia } from '~/hooks/use_match_media';
import s from './toaster.module.scss';

/** How long a toast stays on screen before auto-dismissing. */
const TOAST_DURATION_MS = 3000;

/** Vertical gap: The peek when stacked and the spacing when expanded. */
const ROW_GAP = 16;

/** How much each toast behind the front one shrinks. */
const SCALE_STEP = 0.025;

/** How many toasts stay visible in the collapsed stack. */
const VISIBLE_TOASTS = 3;

/** How far below its resting spot a new toast starts before sliding in. */
const ENTER_OFFSET = 24;

interface Toast {
  id: number;
  title: string;
  description: string;
}

type ToastListener = () => void;

/**
 * Holds the live toast list and notifies subscribers on change. A single
 * module-level instance backs both the `toast()` helper and the `Toaster` view,
 * so toasts can be emitted from anywhere without a provider.
 */
class ToastStore {
  #toasts: Toast[] = [];
  #nextId = 0;
  #listeners = new Set<ToastListener>();

  /** Register a listener; returns an unsubscribe (useSyncExternalStore). */
  subscribe = (listener: ToastListener) => {
    this.#listeners.add(listener);

    return () => {
      this.#listeners.delete(listener);
    };
  };

  /** Current toasts — a stable reference until the next mutation. */
  getSnapshot = () => this.#toasts;

  /** Queue a toast. Returns its id so callers can dismiss it early. */
  add = (title: string, description: string) => {
    const id = this.#nextId++;
    this.#toasts = [...this.#toasts, { id, title, description }];
    this.#emit();
    return id;
  };

  dismiss = (id: number) => {
    this.#toasts = this.#toasts.filter((toast) => toast.id !== id);
    this.#emit();
  };

  #emit = () => {
    for (const listener of this.#listeners) listener();
  };
}

/** Singleton store instance used to manage toasts across the app. */
const TOAST_STORE = new ToastStore();

/** Queue a toast. Returns its id so callers can dismiss it early if needed. */
export const toast = (title: string, description: string) => {
  return TOAST_STORE.add(title, description);
};

/** Subscribes a component to the toast store. */
const useToasts = () => {
  return useSyncExternalStore(
    TOAST_STORE.subscribe,
    TOAST_STORE.getSnapshot,
    TOAST_STORE.getSnapshot,
  );
};

interface ToastItemProps {
  toast: Toast;

  /** Resting transform - computed from the stack / expanded layout. */
  y: number;
  scale: number;
  opacity: number;

  /** Stacking order within the list (front toast highest). */
  stackIndex: number;
  isExpanded: boolean;
  prefersMotion: boolean;
  onResize: (id: number, height: number) => void;
  onDismiss: (id: number) => void;
}

const ToastItem = ({
  toast,
  y,
  scale,
  opacity,
  stackIndex,
  isExpanded,
  prefersMotion,
  onResize,
  onDismiss,
}: ToastItemProps) => {
  const { id, title, description } = toast;

  const containerRef = useRef<HTMLLIElement>(null);

  useEffect(() => {
    // Only start the auto-dismiss timer if the toast isn't expanded. If opened;
    // the timer is effectively 'on hold' until the user stops interacting
    if (!isExpanded) {
      const timeout = setTimeout(() => {
        TOAST_STORE.dismiss(id);
      }, TOAST_DURATION_MS);
      return () => clearTimeout(timeout);
    }
  }, [id, isExpanded]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const resized = () => onResize(id, container.offsetHeight);

    // Trigger on mount
    resized();

    // Listen for resizes so the Toaster can adjust spacing as needed
    const observer = new ResizeObserver(resized);
    observer.observe(container);
    return () => observer.disconnect();
  }, [id, onResize]);

  return (
    <m.li
      ref={containerRef}
      className={s['toast-container']}
      {...(prefersMotion
        ? {
            style: { zIndex: stackIndex },
            initial: { opacity: 0, y: y + ENTER_OFFSET, scale },
            animate: { y, scale, opacity },
            exit: { opacity: 0, scale: 0.95 },
            transition: { duration: 0.3, ease: EASE_OUT },
          }
        : {
            style: {
              zIndex: stackIndex,
              transform: `translateY(${y}px) scale(${scale})`,
              opacity,
            },
          })}
    >
      <div className={s['content-container']}>
        <p className={s.title}>{title}</p>
        <p className={s.description}>{description}</p>
      </div>

      <button
        type="button"
        className={s['button-dismiss']}
        aria-label={`Dismiss notification: ${title}`}
        onClick={() => onDismiss(id)}
      />
    </m.li>
  );
};

export const Toaster = () => {
  const toasts = useToasts();

  const [heights, setHeights] = useState<Record<number, number>>({});
  const [isHovered, setIsHovered] = useState(false);
  const [isFocused, setIsFocused] = useState(false);
  const isExpanded = isHovered || isFocused;

  const prefersMotion = useMatchMedia('prefers-motion');

  const updateHeights = useCallback((id: number, height: number) => {
    setHeights((previous) =>
      previous[id] === height ? previous : { ...previous, [id]: height },
    );
  }, []);

  const dismissed = useCallback((id: number) => {
    TOAST_STORE.dismiss(id);

    // A click focuses the dismiss button; removing it fires no blur, so focus
    // would stay 'stuck' - by clearing it here we fix issue
    setIsFocused(false);
  }, []);

  const [regionHeight, populatedToasts] = useMemo(() => {
    // Newest first so index 0 is the front of the stack.
    const orderedToasts = [...toasts].reverse();

    // Running total of the heights of the toasts in front of the current one;
    // ends the loop holding the height of every toast combined
    let heightsBefore = 0;
    const populatedToasts = orderedToasts.map((toast, index) => {
      const y = -(ROW_GAP * index) - (isExpanded ? heightsBefore : 0);
      const scale = isExpanded ? 1 : 1 - SCALE_STEP * index;
      const opacity = isExpanded || index < VISIBLE_TOASTS ? 1 : 0;
      const stackIndex = orderedToasts.length - index;
      heightsBefore += heights[toast.id] ?? 0;
      return { toast, y, scale, opacity, stackIndex };
    });

    // Expanded shows every toast, collapsed only the front; either way the
    // peeks above add one gap per toast behind the front
    const [frontToast] = orderedToasts;
    const frontHeight = frontToast ? (heights[frontToast.id] ?? 0) : 0;
    const stackHeight = isExpanded ? heightsBefore : frontHeight;
    const gaps = ROW_GAP * Math.max(0, orderedToasts.length - 1);

    return [stackHeight + gaps, populatedToasts];
  }, [heights, isExpanded, toasts]);

  return (
    <m.ol
      className={s.container}
      aria-label="Notifications"
      aria-live="polite"
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      onFocus={() => setIsFocused(true)}
      onBlur={(event) => {
        // Only collapse once focus leaves the region entirely; not when moving
        // between toasts within it
        if (!event.currentTarget.contains(event.relatedTarget)) {
          setIsFocused(false);
        }
      }}
      {...(prefersMotion
        ? {
            animate: { height: regionHeight },
            transition: { duration: 0.3, ease: EASE_OUT },
          }
        : { style: { height: regionHeight } })}
    >
      <AnimatePresence>
        {populatedToasts.map((item) => (
          <ToastItem
            key={item.toast.id}
            toast={item.toast}
            y={item.y}
            scale={item.scale}
            opacity={item.opacity}
            stackIndex={item.stackIndex}
            isExpanded={isExpanded}
            prefersMotion={prefersMotion}
            onResize={updateHeights}
            onDismiss={dismissed}
          />
        ))}
      </AnimatePresence>
    </m.ol>
  );
};
