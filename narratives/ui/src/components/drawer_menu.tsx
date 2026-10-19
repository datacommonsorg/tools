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
 * @fileoverview Renders the mobile menu drawer: the new-chat control and the section links.
 */

import { ArrowRight, X } from 'lucide-react';
import type { ReactNode } from 'react';
import { getInstanceConfig } from '@/src/config/instance_config';
import { resolveNavItems } from '@/src/config/nav_config';
import { useChatSession } from '@/src/hooks/chat_session_context';
import { useHashRoute } from '@/src/hooks/use_hash_route';
import { NewChatIcon } from './icons';
import { Tooltip } from './tooltip';

/**
 * MenuDrawer is the navigation surface below the `lg` breakpoint, where the
 * header's hamburger replaces the icon rail: a panel sliding in from the
 * right (the hamburger lives at the header's right edge) holding the
 * new-chat control and the instance's sections. Above `lg` the rail and the
 * header links cover both, so nothing here renders.
 */

const PANEL_WIDTH = 320;
const FONT_DISPLAY = 'var(--font-display)';
/**
 * Menu-item text, leading icons and the ✕ read as secondary, so they use the
 * lighter "subtle" gray; the trailing chevron is the dark accent.
 */
const COLOR_LABEL = 'var(--color-subtle)';
const COLOR_ARROW = 'var(--color-on-surface)';
const COLOR_ACTIVE = 'var(--color-theme-primary)';
/**
 * Leading-icon column width in the menu rows (NewChatIcon renders at 24px,
 * the M3 leading-icon size). The section-tab dot sits in a box of the same
 * width so tab labels line up with the "New chat" label above.
 */
const MENU_ICON_WIDTH = 24;
const COLOR_TAB_INACTIVE = 'var(--color-muted)';

/** The mobile menu: a right-anchored slide-in panel over a dimmed page. */
export function MenuDrawer() {
  const { newChat, isDrawerOpen, closeDrawer } = useChatSession();
  const { navigation } = getInstanceConfig();
  const navItems = resolveNavItems(navigation);

  // Drives the active-tab highlight in the section nav below.
  const [route] = useHashRoute();
  const activeId = route || 'agent';

  if (!isDrawerOpen) return null;

  return (
    <>
      {/* Click-outside backdrop, dimmed because the panel floats over
          full-width content. */}
      <div
        className="lg:hidden fixed inset-0 z-10 bg-scrim/30"
        onClick={closeDrawer}
        aria-hidden="true"
      />

      <aside
        className="lg:hidden fixed top-0 right-0 h-full bg-surface border-l border-outline shadow-lg z-20 flex flex-col overflow-hidden"
        style={{
          // Cap at PANEL_WIDTH but always leave a peek of the content behind.
          width: `min(${PANEL_WIDTH}px, calc(100vw - 48px))`,
        }}
        aria-label="Menu"
      >
        {/* Close (✕) — top-right corner. */}
        <div className="flex items-center justify-end px-2 py-2 shrink-0">
          <Tooltip label="Close menu" placement="bottom">
            <button
              type="button"
              aria-label="Close menu"
              onClick={closeDrawer}
              className="w-10 h-10 flex items-center justify-center rounded-full hover:bg-button-hover transition-colors"
              style={{ color: COLOR_LABEL }}
            >
              <X size={24} strokeWidth={1.5} />
            </button>
          </Tooltip>
        </div>

        <div className="border-t border-outline shrink-0" />

        <nav className="flex flex-col py-2 shrink-0">
          {/* Starts an empty chat; newChat closes the drawer behind it. */}
          <MenuItem icon={<NewChatIcon />} label="New chat" onClick={newChat} />
        </nav>

        {navItems.length > 0 && (
          <>
            {/* Align the divider with the menu item label text column. */}
            <div
              className="shrink-0"
              style={{
                paddingLeft: 16 + MENU_ICON_WIDTH + 12,
                paddingRight: 16,
              }}
            >
              <div className="border-t border-outline" />
            </div>

            <nav className="flex flex-col py-2 shrink-0" aria-label="Sections">
              {navItems.map((item) => {
                const active = item.id === activeId;
                return (
                  <a
                    key={item.href}
                    href={item.href}
                    aria-current={active ? 'page' : undefined}
                    onClick={closeDrawer}
                    className="w-full flex items-center gap-3 px-4 py-3 no-underline bg-transparent cursor-pointer hover:bg-surface-soft transition-colors"
                  >
                    <span
                      aria-hidden="true"
                      className="flex justify-center shrink-0"
                      style={{ width: MENU_ICON_WIDTH }}
                    >
                      <span
                        className="w-1.5 h-1.5 rounded-full"
                        style={{
                          background: active ? COLOR_ACTIVE : 'transparent',
                        }}
                      />
                    </span>
                    <span
                      style={{
                        fontFamily: FONT_DISPLAY,
                        fontSize: 15,
                        lineHeight: '20px',
                        fontWeight: 500,
                        color: active ? COLOR_ACTIVE : COLOR_TAB_INACTIVE,
                      }}
                    >
                      {item.label}
                    </span>
                  </a>
                );
              })}
            </nav>
          </>
        )}
      </aside>
    </>
  );
}

/**
 * A single tappable row in the menu: leading icon + label on the left, a dark
 * trailing chevron on the right. The whole row is the button.
 */
function MenuItem({
  icon,
  label,
  onClick,
}: Readonly<{
  icon: ReactNode;
  label: string;
  onClick: () => void;
}>) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="w-full flex items-center justify-between gap-3 px-4 py-3 text-left bg-transparent border-0 cursor-pointer hover:bg-surface-soft transition-colors"
    >
      <span
        className="flex items-center gap-3"
        style={{ color: COLOR_TAB_INACTIVE }}
      >
        {icon}
        <span
          style={{
            fontFamily: FONT_DISPLAY,
            fontSize: 15,
            lineHeight: '20px',
            fontWeight: 500,
          }}
        >
          {label}
        </span>
      </span>
      <ArrowRight size={20} strokeWidth={1.5} style={{ color: COLOR_ARROW }} />
    </button>
  );
}
