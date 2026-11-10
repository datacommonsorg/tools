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
 * @fileoverview Link primitive classifying internal (`#...`, `/...`), external
 * (`http:`, `https:`), and unsafe URLs, enforcing `rel="noopener noreferrer"`
 * on external and new-tab anchors and falling back to an inert `<span>` when
 * `href` is unsafe or malformed.
 */

import type { ComponentPropsWithRef, ReactNode } from 'react';

const HTTP_SCHEME_PREFIX = /^https?:\/\//i;
const INTERNAL_ORIGIN = 'https://narratives.invalid';
const MAX_ASCII_C0_CODE = 0x1f;
const ASCII_DEL_CODE = 0x7f;

const hasAsciiControlChar = (value: string): boolean => {
  for (let index = 0; index < value.length; index += 1) {
    const code = value.charCodeAt(index);
    if (code <= MAX_ASCII_C0_CODE || code === ASCII_DEL_CODE) {
      return true;
    }
  }
  return false;
};

/** Classification of a candidate link `href`. */
export type LinkKind = 'internal' | 'external' | 'unsafe';

/**
 * Classifies `value` as `'internal'` (`#...` fragment or single-slash `/...`
 * root-relative path), `'external'` (well-formed `http:` or `https:` URL), or
 * `'unsafe'` (disallowed scheme, backslash, ASCII control character,
 * protocol-relative `//...`, bare non-path string, or malformed URL).
 */
export const classifyLinkHref = (value: string): LinkKind => {
  if (!value || value.includes('\\') || hasAsciiControlChar(value)) {
    return 'unsafe';
  }
  if (value.startsWith('#')) {
    return 'internal';
  }
  if (value.startsWith('/') && !value.startsWith('//')) {
    try {
      const parsed = new URL(value, INTERNAL_ORIGIN);
      return parsed.origin === INTERNAL_ORIGIN ? 'internal' : 'unsafe';
    } catch {
      // new URL throws TypeError on unparseable paths; treat them as unsafe.
      return 'unsafe';
    }
  }
  if (!HTTP_SCHEME_PREFIX.test(value)) {
    return 'unsafe';
  }
  try {
    const parsed = new URL(value);
    return parsed.protocol === 'http:' || parsed.protocol === 'https:'
      ? 'external'
      : 'unsafe';
  } catch {
    // new URL throws TypeError on unparseable strings; treat them as unsafe.
    return 'unsafe';
  }
};

/** Props for {@link Link}. */
export interface LinkProps
  extends Omit<ComponentPropsWithRef<'a'>, 'href' | 'rel'> {
  href: string;
  children: ReactNode;
}

/**
 * Renders an `<a>` inferred from `href` (same-tab for internal `#...` and `/...`
 * targets; `target="_blank" rel="noopener noreferrer"` by default for external
 * `http(s)` URLs), or an inert `<span>` when `href` is unsafe or malformed so
 * untrusted text stays visible without rendering an executable or broken link.
 */
export const Link = ({
  href,
  children,
  target,
  id,
  title,
  className,
  ...anchorProps
}: LinkProps) => {
  const kind = classifyLinkHref(href);
  if (kind === 'unsafe') {
    return (
      <span id={id} title={title} className={className}>
        {children}
      </span>
    );
  }
  const resolvedTarget = target ?? (kind === 'external' ? '_blank' : undefined);
  const opensOtherContext =
    resolvedTarget !== undefined &&
    resolvedTarget !== '' &&
    resolvedTarget.toLowerCase() !== '_self';
  const rel =
    kind === 'external' || opensOtherContext
      ? 'noopener noreferrer'
      : undefined;
  return (
    <a
      {...anchorProps}
      href={href}
      target={resolvedTarget}
      rel={rel}
      id={id}
      title={title}
      className={className}
    >
      {children}
    </a>
  );
};
