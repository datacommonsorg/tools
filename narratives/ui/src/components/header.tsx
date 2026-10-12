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

import { getInstanceConfig } from '@/src/config/instance_config';
import { resolveNavItems } from '@/src/config/nav_config';
import { useChatSession } from '@/src/hooks/chat_session_context';
import { useHashRoute } from '@/src/hooks/use_hash_route';
import { MenuIcon } from './icons';
import { Tooltip } from './tooltip';

/** Renders the instance logo, wordmark, and primary navigation links. */
export function Header() {
  const [route] = useHashRoute();
  const { logoUrl, logoAlt, logoText, instanceName, navigation } =
    getInstanceConfig();
  const navItems = resolveNavItems(navigation);
  const activeId = route || 'agent';
  const { toggleDrawer, isDrawerOpen } = useChatSession();

  // Leave the alternative text empty when the wordmark is displayed next to
  // the logo so screen readers do not announce the instance name twice.
  const logoAltText = logoText
    ? ''
    : logoAlt || `${instanceName || 'Data Commons'} logo`;

  return (
    <header className="w-full flex items-center justify-between gap-3 px-3 sm:px-6 lg:px-12 py-4 sm:py-5 shrink-0">
      <div className="flex items-center gap-2 select-none shrink-0">
        <img
          src={logoUrl}
          alt={logoAltText}
          className="w-auto object-contain"
          style={{ height: 'var(--logo-height)' }}
        />
        {logoText && (
          <span className="text-body-large-emphasized text-on-surface whitespace-nowrap">
            {logoText}
          </span>
        )}
      </div>

      {navItems.length > 0 && (
        <nav
          aria-label="Primary"
          className="flex items-center gap-4 md:gap-6 lg:gap-8 text-label-large text-on-surface-variant ml-auto whitespace-nowrap overflow-x-auto no-scrollbar"
        >
          {navItems.map((item) => {
            const isActive = item.id === activeId;
            // Use the href as the React key because multiple external links
            // share the same empty derived route ID.
            // Hide header navigation links below the lg breakpoint because the
            // mobile drawer provides primary navigation on narrow viewports.
            return (
              <a
                key={item.href}
                href={item.href}
                aria-current={isActive ? 'page' : undefined}
                className={`relative py-1 shrink-0 transition-colors hidden lg:block ${
                  isActive
                    ? 'font-medium text-nav-active'
                    : 'hover:text-on-surface'
                }`}
              >
                {item.label}
                {isActive && (
                  <span className="absolute top-0 left-0 w-full h-0.5 rounded-b-sm bg-nav-active" />
                )}
              </a>
            );
          })}
        </nav>
      )}

      {/* Show the mobile menu button below the lg breakpoint where the sidebar rail is hidden. */}
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
    </header>
  );
}
