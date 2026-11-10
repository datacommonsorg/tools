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
 * @fileoverview Helpers for normalizing configured origin URLs
 * (`VITE_DC_API_ROOT`) and resolving application-relative paths against the
 * active document URL.
 */

const LEADING_SLASHES_PATTERN = /^\/+/;
const TRAILING_SLASHES_PATTERN = /\/+$/;
const SHELL_FILENAME_SUFFIX = /\/index\.html$/;

/** Trims surrounding whitespace and trailing slashes from a URL or path. */
export const trimTrailingSlashes = (value: string): string =>
  value.trim().replace(TRAILING_SLASHES_PATTERN, '');

/**
 * Resolves an application-relative path against `window.location.pathname` so
 * the same compiled UI bundle resolves assets and `/agent/*` endpoints whether
 * mounted at `/` or under a runtime `BASE_PATH` subpath (such as
 * `/labs/discover/`), with or without a trailing slash.
 */
export const withBaseUrl = (path: string): string => {
  const cleanPath = path.trim().replace(LEADING_SLASHES_PATTERN, '');
  if (typeof window === 'undefined') {
    return `/${cleanPath}`;
  }
  const rawPathname = window.location.pathname.replace(
    SHELL_FILENAME_SUFFIX,
    '/',
  );
  const basePrefix = trimTrailingSlashes(rawPathname).replace(
    LEADING_SLASHES_PATTERN,
    '',
  );
  return basePrefix ? `/${basePrefix}/${cleanPath}` : `/${cleanPath}`;
};
