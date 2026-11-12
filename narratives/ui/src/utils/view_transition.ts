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
 * @fileoverview Limits the cross-document view transition opted into by
 * `@view-transition` in index.html to navigations from this app to same-origin
 * Data Commons pages outside the app's base path.
 *
 * Only the outgoing side is filtered: a transition skipped in the old page's
 * `pageswap` never reaches the new page, so app-to-app navigations are covered
 * here and Data Commons pages filter their own outgoing navigations. That
 * keeps this out of a render-blocking `pagereveal` script in index.html.
 */

import { getBasePath } from '@/src/config/base_url';

/**
 * `PageSwapEvent` fields used here; TypeScript's DOM lib does not ship it.
 * Delete this and the `WindowEventMap` augmentation once it does, or the two
 * declarations conflict on upgrade.
 */
interface PageSwapEvent extends Event {
  readonly viewTransition: ViewTransition | null;
  readonly activation: {
    readonly entry: { readonly url: string | null };
  } | null;
}

declare global {
  interface WindowEventMap {
    pageswap: PageSwapEvent;
  }
}

/**
 * Whether `url` is a same-origin page outside the app mounted at `basePath`.
 * Always false when the app is mounted at the root, since every same-origin
 * page then belongs to the app.
 */
export const isOutsideApp = (
  url: string | null | undefined,
  basePath: string,
): boolean => {
  if (!basePath || !url) {
    return false;
  }
  const { pathname } = new URL(url);
  return pathname !== basePath && !pathname.startsWith(`${basePath}/`);
};

/**
 * Skips the view transition when leaving for anything other than a Data
 * Commons page outside the app, including cross-origin pages, whose
 * `activation` is null. Returns a function that removes the listener.
 */
export const registerViewTransitionFilter = (): (() => void) => {
  const basePath = getBasePath();
  const onPageSwap = (event: PageSwapEvent) => {
    if (
      event.viewTransition &&
      !isOutsideApp(event.activation?.entry.url, basePath)
    ) {
      event.viewTransition.skipTransition();
    }
  };
  window.addEventListener('pageswap', onPageSwap);
  return () => window.removeEventListener('pageswap', onPageSwap);
};
