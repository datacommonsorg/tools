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
 * @fileoverview Renders the top navigation header with the instance logo,
 * wordmark, and primary navigation links.
 */

import { MenuIcon } from '@/src/components/icons';
import { classifyLinkHref, Link } from '@/src/components/link';
import { Tooltip } from '@/src/components/tooltip';
import { getBasePath } from '@/src/config/base_url';
import { getInstanceConfig } from '@/src/config/instance_config';
import { resolveNavItems } from '@/src/config/nav_config';
import { getRuntimeConfig } from '@/src/config/runtime_config';
import { useChatSession } from '@/src/hooks/chat_session_context';
import { useHashRoute } from '@/src/hooks/use_hash_route';

/** Returns the state classes for a header navigation tab. */
function getNavTabStateClass(isActive: boolean): string {
  if (isActive) {
    return 'font-medium text-nav-active';
  }
  return 'hover:text-on-surface';
}

/** Renders the instance logo, wordmark, and primary navigation links. */
export function Header() {
  const [route] = useHashRoute();
  const { logoUrl, logoAlt, logoHref, logoText, instanceName, navigation } =
    getInstanceConfig();
  const navItems = resolveNavItems(navigation);
  const activeId = route || 'agent';
  const { toggleDrawer, isDrawerOpen } = useChatSession();
  const { isChatEnabled } = getRuntimeConfig();
  // The drawer holds New chat while chat is enabled, and the section links.
  const hasDrawerItems = isChatEnabled || navItems.length > 0;

  // Leave the alternative text empty when the wordmark is displayed next to
  // the logo so screen readers do not announce the instance name twice.
  const logoAltText = logoText
    ? ''
    : logoAlt || `${instanceName || 'Data Commons'} logo`;
  // At the site root, a same-origin logo link would reload the app and drop
  // the current chat, so the logo stays plain unless it leaves the app.
  const logoHrefKind = classifyLinkHref(logoHref);
  const isLogoLinked =
    logoHrefKind === 'external' ||
    (logoHrefKind === 'internal' && getBasePath() !== '');
  const logo = (
    <>
      <img
        src={logoUrl}
        alt={logoAltText}
        className="w-auto object-contain"
        style={{ height: 'var(--logo-height)' }}
      />
      {logoText && (
        <span className="text-wordmark text-on-chrome whitespace-nowrap">
          {logoText}
        </span>
      )}
    </>
  );

  return (
    <header className="sticky top-0 z-5 bg-chrome lg:-ml-rail flex items-center justify-between gap-3 px-5 py-4 shrink-0 shadow-header motion-safe:animate-fade-in">
      {isLogoLinked ? (
        // `target="_self"` keeps external targets in this tab; `py-2 -my-2`
        // gives a 44px touch target without changing the header height.
        <Link
          href={logoHref}
          target="_self"
          className="flex items-center gap-4 select-none shrink-0 motion-safe:animate-nudge-from-left py-2 -my-2 rounded-sm focus-visible:outline-offset-2"
        >
          {logo}
        </Link>
      ) : (
        <div className="flex items-center gap-4 select-none shrink-0 motion-safe:animate-nudge-from-left">
          {logo}
        </div>
      )}

      {navItems.length > 0 && (
        // Hide header navigation below the lg breakpoint because the mobile
        // drawer provides primary navigation on narrow viewports.
        <nav
          aria-label="Primary"
          className="hidden lg:flex items-center gap-8 text-label-large text-on-surface-variant ml-auto whitespace-nowrap overflow-x-auto no-scrollbar"
        >
          {navItems.map((item) => {
            const isActive = item.id === activeId;
            // Use the href as the React key because multiple external links
            // share the same empty derived route ID.
            return (
              <Link
                key={item.href}
                href={item.href}
                target="_self"
                aria-current={isActive ? 'page' : undefined}
                className={`relative py-1 shrink-0 transition-colors ${getNavTabStateClass(
                  isActive,
                )}`}
              >
                {item.label}
                {isActive && (
                  <span className="absolute top-0 left-0 w-full h-0.5 rounded-b-sm bg-nav-active" />
                )}
              </Link>
            );
          })}
        </nav>
      )}

      {/* Show the mobile menu button below the lg breakpoint where the sidebar
          rail is hidden, and only when the drawer has an item to show. */}
      {hasDrawerItems && (
        <Tooltip label="Menu" placement="bottom">
          <button
            type="button"
            aria-label="Open menu"
            aria-expanded={isDrawerOpen}
            onClick={toggleDrawer}
            className={`lg:hidden shrink-0 ml-1 w-10 h-10 flex items-center justify-center rounded-full transition-colors ${
              isDrawerOpen
                ? 'bg-button-hover text-on-surface'
                : 'hover:bg-button-hover text-on-surface-variant'
            }`}
          >
            <MenuIcon size="lg" />
          </button>
        </Tooltip>
      )}
    </header>
  );
}
