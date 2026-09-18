/*
 * Copyright 2026 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     https://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

/**
 * @fileoverview Simple FIFO (First-In, First-Out) cache helper to store
 * and evict API responses and metadata.
 */

import { DataCommonsClient } from './types';

export const MAX_CACHE_SIZE = 50;

/**
 * Helper to set values in client cache enforcing maximum cache size
 * (FIFO eviction).
 */
export function setCache(
  state: DataCommonsClient,
  key: string,
  value: unknown
): void {
  if (!state.cache.has(key) && state.cache.size >= MAX_CACHE_SIZE) {
    const oldestKey = state.cache.keys().next().value as string | undefined;
    if (oldestKey !== undefined) {
      state.cache.delete(oldestKey);
    }
  }
  state.cache.set(key, value);
}
