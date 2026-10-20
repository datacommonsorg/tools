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
 * @fileoverview Helpers for normalizing build-time base URLs (`VITE_BASE_PATH`,
 * `VITE_DC_API_ROOT`) and resolving root-relative paths under Vite's
 * `BASE_URL`.
 */

const LEADING_SLASHES_PATTERN = /^\/+/;
const TRAILING_SLASHES_PATTERN = /\/+$/;

/** Trims surrounding whitespace and trailing slashes from a URL or path. */
export const trimTrailingSlashes = (value: string): string =>
  value.trim().replace(TRAILING_SLASHES_PATTERN, '');

/**
 * Normalizes a raw base path into Vite's `/<subpath>/` format, or `'/'` when
 * empty or root.
 */
export const normalizeBasePath = (rawBasePath?: string): string => {
  const stripped = trimTrailingSlashes(rawBasePath ?? '').replace(
    LEADING_SLASHES_PATTERN,
    '',
  );
  return stripped ? `/${stripped}/` : '/';
};

/**
 * Prefixes a root-relative path with Vite's `BASE_URL` so root builds resolve
 * to `/<path>` and subpath builds resolve to `/<subpath>/<path>`.
 */
export const withBaseUrl = (path: string): string => {
  const base = trimTrailingSlashes(import.meta.env.BASE_URL || '/');
  const cleanPath = path.trim().replace(LEADING_SLASHES_PATTERN, '');
  return `${base}/${cleanPath}`;
};
