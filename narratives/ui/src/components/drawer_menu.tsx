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
import { type ReactNode, useEffect } from 'react';
import { getInstanceConfig } from '@/src/config/instance_config';
import { resolveNavItems } from '@/src/config/nav_config';
import { useChatSession } from '@/src/hooks/chat_session_context';
import { useHashRoute } from '@/src/hooks/use_hash_route';
import { NewChatIcon } from './icons';
import { Tooltip } from './tooltip';

/**
 * The navigation surface below the `lg` breakpoint, where the header's
 * hamburger replaces the icon rail. Above `lg` nothing here renders.
 */

/** Typography shared by every row label in the menu. */
const ROW_LABEL_CLASSES = 'font-display text-[15px] leading-5 font-medium';

/** The mobile menu: a right-anchored slide-in panel over a dimmed page. */
export function MenuDrawer() {
  const { newChat, isDrawerOpen, closeDrawer } = useChatSession();
  const { navigation } = getInstanceConfig();
  const navItems = resolveNavItems(navigation);

  // Drives the active-tab highlight in the section nav below.
  const [route] = useHashRoute();
  const activeId = route || 'agent';

  useEffect(() => {
    if (!isDrawerOpen) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') closeDrawer();
    };
    document.addEventListener('keydown', closeOnEscape);
    return () => document.removeEventListener('keydown', closeOnEscape);
  }, [isDrawerOpen, closeDrawer]);

  if (!isDrawerOpen) return null;

  return (
    <>
      {/* Pointer-only; Escape and the close button serve the keyboard. */}
      <div
        className="lg:hidden fixed inset-0 z-10 bg-scrim/30"
        onClick={closeDrawer}
        aria-hidden="true"
      />

      <aside
        className="lg:hidden fixed top-0 right-0 h-full w-[calc(100vw-3rem)] max-w-80 bg-surface border-l border-outline shadow-lg z-20 flex flex-col overflow-hidden"
        aria-label="Menu"
      >
        {/* Close (✕) — top-right corner. */}
        <div className="flex items-center justify-end px-2 py-2 shrink-0">
          <Tooltip label="Close menu" placement="bottom">
            <button
              type="button"
              aria-label="Close menu"
              onClick={closeDrawer}
              className="w-11 h-11 flex items-center justify-center rounded-full text-subtle hover:bg-button-hover transition-colors"
            >
              <X strokeWidth={1.5} aria-hidden="true" />
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
            <div className="shrink-0 pl-13 pr-4">
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
                      className="flex justify-center w-6 shrink-0"
                    >
                      <span
                        className={`w-1.5 h-1.5 rounded-full ${active ? 'bg-theme-primary' : 'bg-transparent'}`}
                      />
                    </span>
                    <span
                      className={`${ROW_LABEL_CLASSES} ${active ? 'text-theme-primary' : 'text-muted'}`}
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

/** Props for {@link MenuItem}. */
interface MenuItemProps {
  icon: ReactNode;
  label: string;
  onClick: () => void;
}

/**
 * A single tappable row in the menu: leading icon + label on the left, a dark
 * trailing chevron on the right. The whole row is the button.
 */
function MenuItem({ icon, label, onClick }: Readonly<MenuItemProps>) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="w-full flex items-center justify-between gap-3 px-4 py-3 text-left bg-transparent border-0 cursor-pointer hover:bg-surface-soft transition-colors"
    >
      <span className="flex items-center gap-3 text-muted">
        {icon}
        <span className={ROW_LABEL_CLASSES}>{label}</span>
      </span>
      <ArrowRight
        strokeWidth={1.5}
        className="size-5 text-on-surface"
        aria-hidden="true"
      />
    </button>
  );
}
