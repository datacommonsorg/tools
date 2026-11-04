/**
 * Copyright 2026 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
 * implied. See the License for the specific language governing
 * permissions and limitations under the License.
 */

/**
 * @fileoverview Hook for detecting debug mode from the ?debug query parameter
 * or the debug report mode `on` reported by the /agent/health endpoint.
 */

import { useEffect, useState } from 'react';
import { withBaseUrl } from '@/src/config/base_url';

const DEBUG_QUERY_PARAM = 'debug';

const ENABLED_DEBUG_VALUES: ReadonlySet<string> = new Set(['', 'true', '1']);

let cachedServerDebugOn: boolean | null = null;
let inFlightHealthRequest: Promise<boolean> | null = null;

/**
 * Resets the module-level /agent/health debug cache. For testing only.
 */
export const resetDebugModeCacheForTests = (): void => {
  cachedServerDebugOn = null;
  inFlightHealthRequest = null;
};

/**
 * Reports whether the URL query string search enables debug mode (?debug,
 * ?debug=, ?debug=true, or ?debug=1, case-insensitively after trimming).
 *
 * Rejects absent parameters and legacy or falsy values such as 'provenance',
 * 'false', or '0'.
 */
export const isDebugUrlEnabled = (search: string): boolean => {
  const rawValue = new URLSearchParams(search).get(DEBUG_QUERY_PARAM);
  if (rawValue === null) {
    return false;
  }
  return ENABLED_DEBUG_VALUES.has(rawValue.trim().toLowerCase());
};

const fetchServerDebugMode = async (): Promise<boolean> => {
  if (cachedServerDebugOn !== null) {
    return cachedServerDebugOn;
  }
  if (inFlightHealthRequest !== null) {
    return inFlightHealthRequest;
  }
  inFlightHealthRequest = (async (): Promise<boolean> => {
    try {
      const response = await fetch(withBaseUrl('/agent/health'));
      if (!response.ok) {
        cachedServerDebugOn = false;
        return false;
      }
      const data: unknown = await response.json();
      const isOn =
        typeof data === 'object' &&
        data !== null &&
        !Array.isArray(data) &&
        (data as { debug_report?: unknown }).debug_report === 'on';
      cachedServerDebugOn = isOn;
      return isOn;
    } catch {
      cachedServerDebugOn = false;
      return false;
    } finally {
      inFlightHealthRequest = null;
    }
  })();
  return inFlightHealthRequest;
};

/**
 * Reports whether debug mode is enabled, either via URL query (?debug) or by
 * server configuration (debug report mode `on` via /agent/health).
 *
 * @param enabled Whether debug detection should actively query /agent/health
 *   when URL debug is inactive. When false, avoids issuing network requests.
 */
export const useDebugMode = (enabled = true): boolean => {
  const isUrlEnabled =
    typeof window !== 'undefined' && isDebugUrlEnabled(window.location.search);

  const [serverDebugOn, setServerDebugOn] = useState<boolean>(() =>
    isUrlEnabled ? true : (cachedServerDebugOn ?? false),
  );

  useEffect(() => {
    if (isUrlEnabled || !enabled) {
      return;
    }
    if (cachedServerDebugOn !== null) {
      if (cachedServerDebugOn && !serverDebugOn) {
        setServerDebugOn(true);
      }
      return;
    }
    let cancelled = false;
    void fetchServerDebugMode().then((isOn) => {
      if (!cancelled && isOn) {
        setServerDebugOn(true);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [isUrlEnabled, enabled, serverDebugOn]);

  return isUrlEnabled || serverDebugOn;
};
