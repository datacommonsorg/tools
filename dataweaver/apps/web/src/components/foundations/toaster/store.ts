import { useSyncExternalStore } from 'react';

export interface Toast {
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

  /** Register a listener and returns an unsubscribe. */
  subscribe = (listener: ToastListener) => {
    this.#listeners.add(listener);
    return () => this.#listeners.delete(listener);
  };

  /** Current toasts — a stable reference until the next mutation. */
  getSnapshot = () => this.#toasts;

  /** Queue a toast. Returns its ID so callers can dismiss it early. */
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
export const TOAST_STORE = new ToastStore();

/** Queue a toast. Returns its id so callers can dismiss it early if needed. */
export const toast = (title: string, description: string) => {
  return TOAST_STORE.add(title, description);
};

/** Subscribes a component to the toast store. */
export const useToasts = () => {
  return useSyncExternalStore(
    TOAST_STORE.subscribe,
    TOAST_STORE.getSnapshot,
    TOAST_STORE.getSnapshot,
  );
};
