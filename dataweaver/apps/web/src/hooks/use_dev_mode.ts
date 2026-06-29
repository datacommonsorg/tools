'use client';

import { useSyncExternalStore } from 'react';

const getSnapshot = (): boolean => {
  const params = new URLSearchParams(window.location.search);
  return params.get('dev') === 'true';
};

const getServerSnapshot = (): boolean => false;

// The query string doesn't change at runtime in this app,
// so no subscription is needed.
const subscribe = (_onStoreChange: () => void): (() => void) => {
  return () => {
    /* noop — URL params are static */
  };
};

/** Returns `true` when the URL contains `?dev=true`. */
export const useDevMode = (): boolean =>
  useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
