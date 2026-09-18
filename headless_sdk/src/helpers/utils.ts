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
 * @fileoverview Generic core object utilities, including deep freezing and
 * property resolution.
 */

import { V2NodePropertyValue } from '../types_api';

/**
 * Safely extracts the first property value from node property records.
 * Resolves standard value fields, display name strings, or node DCID links.
 *
 * @param nodeData Map containing nodes values.
 * @param property Property key name to lookup (e.g. 'name').
 * @returns The resolved string value, or undefined.
 */
export function getFirstPropertyValue(
  nodeData: Record<string, (V2NodePropertyValue | string)[]> | undefined,
  property: string
): string | undefined {
  const val = nodeData?.[property]?.[0];
  if (!val) return undefined;
  if (typeof val === 'string') return val;
  return val.value || val.name || val.dcid || undefined;
}

/**
 * Recursively deep freezes a JavaScript object or array structure to enforce
 * SDK immutability for responses returned to consumers.
 *
 * @param obj Target javascript object or array structure to freeze.
 * @returns The frozen read-only structure.
 */
export function deepFreeze<T>(obj: T): T {
  if (obj === null || typeof obj !== 'object') {
    return obj;
  }
  Object.freeze(obj);
  Object.getOwnPropertyNames(obj).forEach((prop) => {
    const propVal = (obj as Record<string, unknown>)[prop];
    if (
      propVal !== null &&
      (typeof propVal === 'object' || typeof propVal === 'function') &&
      !Object.isFrozen(propVal)
    ) {
      deepFreeze(propVal);
    }
  });
  return obj;
}
