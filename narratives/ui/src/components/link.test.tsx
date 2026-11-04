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
 * @fileoverview Tests for the `Link` primitive and `classifyLinkHref`.
 */

import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import type { MouseEvent } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { classifyLinkHref, Link } from '@/src/components/link';

afterEach(() => {
  cleanup();
});

describe('classifyLinkHref', () => {
  it('classifies fragments and single-slash root-relative paths as internal', () => {
    // Test: Internal SPA navigation and in-page anchor targets.
    // Situation: Hash fragments and root-relative paths are passed.
    // Expectation: Each classifies as "internal".
    expect(classifyLinkHref('#')).toBe('internal');
    expect(classifyLinkHref('#/metrics')).toBe('internal');
    expect(classifyLinkHref('#citation-0-1')).toBe('internal');
    expect(classifyLinkHref('/')).toBe('internal');
    expect(classifyLinkHref('/about?tab=sources#top')).toBe('internal');
  });

  it('classifies absolute http and https URLs as external', () => {
    // Test: Valid external HTTP(S) URLs.
    // Situation: Well-formed http:// and https:// URLs, including uppercase schemes.
    // Expectation: Both classify as "external".
    expect(classifyLinkHref('https://datacommons.org/browser/Earth')).toBe(
      'external',
    );
    expect(classifyLinkHref('HTTP://example.org/dataset?id=1')).toBe(
      'external',
    );
  });

  it('classifies executable and non-HTTP schemes as unsafe', () => {
    // Test: Disallowed URI schemes.
    // Situation: javascript:, data:, ftp:, and mailto: URLs are passed.
    // Expectation: Every non-HTTP(S) scheme classifies as "unsafe".
    expect(classifyLinkHref('javascript:alert(1)')).toBe('unsafe');
    expect(classifyLinkHref('data:text/html,<script>alert(1)</script>')).toBe(
      'unsafe',
    );
    expect(classifyLinkHref('ftp://example.org/file.csv')).toBe('unsafe');
    expect(classifyLinkHref('mailto:info@example.org')).toBe('unsafe');
  });

  it('classifies URLs containing backslashes or control characters as unsafe', () => {
    // Test: Backslash and ASCII control-character normalization ambiguity.
    // Situation: URLs with backslashes or embedded tabs/newlines are passed.
    // Expectation: Every ambiguous input classifies as "unsafe".
    expect(classifyLinkHref('https:\\\\evil.example')).toBe('unsafe');
    expect(classifyLinkHref('https://trusted.example\\@evil.example')).toBe(
      'unsafe',
    );
    expect(classifyLinkHref('/\\evil.example')).toBe('unsafe');
    expect(classifyLinkHref('/\t/evil.example')).toBe('unsafe');
  });

  it('classifies empty, protocol-relative, bare, and malformed strings as unsafe', () => {
    // Test: Non-path strings and unparseable inputs.
    // Situation: Empty strings, protocol-relative URLs, bare labels, and
    //   malformed authorities are passed.
    // Expectation: Every input classifies as "unsafe".
    expect(classifyLinkHref('')).toBe('unsafe');
    expect(classifyLinkHref('//example.org/protocol-relative')).toBe('unsafe');
    expect(classifyLinkHref('///example.org/triple-slash')).toBe('unsafe');
    expect(classifyLinkHref('World Bank')).toBe('unsafe');
    expect(classifyLinkHref('relative/without-leading-slash')).toBe('unsafe');
    expect(classifyLinkHref('https://')).toBe('unsafe');
    expect(classifyLinkHref('http://[invalid')).toBe('unsafe');
  });
});

describe('Link', () => {
  it('renders an external URL in _blank with noopener noreferrer by default', () => {
    // Test: Default external link rendering.
    // Situation: Link receives an https:// URL, title, and className.
    // Expectation: An anchor opens in _blank with rel="noopener noreferrer".
    const url = 'https://example.org/source';
    render(
      <Link href={url} title="Source URL" className="link-style">
        {url}
      </Link>,
    );

    const link = screen.getByRole('link', { name: url });
    expect(link.getAttribute('href')).toBe(url);
    expect(link.getAttribute('target')).toBe('_blank');
    expect(link.getAttribute('rel')).toBe('noopener noreferrer');
    expect(link.getAttribute('title')).toBe('Source URL');
    expect(link.className).toBe('link-style');
  });

  it('renders an internal URL in the current tab without target or rel', () => {
    // Test: Internal link rendering and anchor attribute forwarding.
    // Situation: Link receives a hash route with aria-current and onClick.
    // Expectation: An anchor renders without target or rel and forwards props.
    const handleClick = vi.fn((event: MouseEvent<HTMLAnchorElement>) => {
      event.preventDefault();
    });
    render(
      <Link href="#/metrics" aria-current="page" onClick={handleClick}>
        Metrics
      </Link>,
    );

    const link = screen.getByRole('link', { name: 'Metrics' });
    expect(link.getAttribute('href')).toBe('#/metrics');
    expect(link.getAttribute('target')).toBeNull();
    expect(link.getAttribute('rel')).toBeNull();
    expect(link.getAttribute('aria-current')).toBe('page');
    fireEvent.click(link);
    expect(handleClick).toHaveBeenCalledTimes(1);
  });

  it('honors an explicit target override while keeping noopener noreferrer when needed', () => {
    // Test: Explicit target override on external and internal links.
    // Situation: An external link sets target="_self", while internal links set
    //   target="_blank", target="preview", and target="_self".
    // Expectation: External and auxiliary-context targets keep
    //   rel="noopener noreferrer", while same-tab internal target="_self" omits rel.
    render(
      <>
        <Link href="https://datacommons.org" target="_self">
          Same-tab external
        </Link>
        <Link href="#/metrics" target="_blank">
          New-tab internal
        </Link>
        <Link href="/about" target="preview">
          Named-window internal
        </Link>
        <Link href="/about" target="_self">
          Same-tab internal
        </Link>
      </>,
    );

    const sameTabExternal = screen.getByRole('link', {
      name: 'Same-tab external',
    });
    expect(sameTabExternal.getAttribute('target')).toBe('_self');
    expect(sameTabExternal.getAttribute('rel')).toBe('noopener noreferrer');

    const newTabInternal = screen.getByRole('link', {
      name: 'New-tab internal',
    });
    expect(newTabInternal.getAttribute('target')).toBe('_blank');
    expect(newTabInternal.getAttribute('rel')).toBe('noopener noreferrer');

    const namedWindowInternal = screen.getByRole('link', {
      name: 'Named-window internal',
    });
    expect(namedWindowInternal.getAttribute('target')).toBe('preview');
    expect(namedWindowInternal.getAttribute('rel')).toBe('noopener noreferrer');

    const sameTabInternal = screen.getByRole('link', {
      name: 'Same-tab internal',
    });
    expect(sameTabInternal.getAttribute('target')).toBe('_self');
    expect(sameTabInternal.getAttribute('rel')).toBeNull();
  });

  it('falls back to an inert span when the URL is unsafe', () => {
    // Test: Unsafe URL fallback rendering.
    // Situation: Link receives a javascript: URL and an onClick handler.
    // Expectation: No anchor renders, text and metadata stay on a span, and
    //   onClick is not attached to the non-interactive span.
    const unsafeHref = 'javascript:alert(1)';
    const handleClick = vi.fn();
    render(
      <Link
        href={unsafeHref}
        title={unsafeHref}
        className="fallback"
        onClick={handleClick}
      >
        {unsafeHref}
      </Link>,
    );

    expect(screen.queryByRole('link')).toBeNull();
    const fallback = screen.getByText(unsafeHref);
    expect(fallback.tagName).toBe('SPAN');
    expect(fallback.getAttribute('href')).toBeNull();
    expect(fallback.getAttribute('title')).toBe(unsafeHref);
    expect(fallback.className).toBe('fallback');
    fireEvent.click(fallback);
    expect(handleClick).not.toHaveBeenCalled();
  });
});
