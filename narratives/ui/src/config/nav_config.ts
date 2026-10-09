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
 * @fileoverview Resolves the instance navigation entries into header tabs.
 */

import type { NavLink } from './instance_config';

export interface NavItem {
  id: string;
  label: string;
  href: string;
}

/**
 * Extracts the in-app route identifier from a navigation href (for example,
 * `#/metrics` becomes `metrics`). External URLs return an empty string so their
 * hash fragments cannot match an in-app route.
 */
function deriveNavId(href: string): string {
  if (/^https?:\/\//i.test(href)) {
    return '';
  }
  const hashIndex = href.indexOf('#');
  const path = hashIndex >= 0 ? href.slice(hashIndex + 1) : href;
  const segment = path.replace(/^\/+/, '').split('/')[0] ?? '';
  return segment || (hashIndex >= 0 ? 'agent' : '');
}

/** Maps navigation links to `NavItem` entries with derived route identifiers. */
export function resolveNavItems(navigation: NavLink[]): NavItem[] {
  return navigation.map((item) => ({
    id: deriveNavId(item.href),
    label: item.label,
    href: item.href,
  }));
}
