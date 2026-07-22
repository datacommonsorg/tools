import { AnimatePresence, m } from 'motion/react';
import type { ComponentPropsWithRef, ComponentType, ReactNode } from 'react';
import { useEffect, useId, useRef } from 'react';
import s from './conditional_tabs.module.scss';

interface Tab {
  icon: ComponentType<ComponentPropsWithRef<'svg'>>;

  /** **Note**: Make sure each label is unique as it's used as key. */
  label: string;
  children: ReactNode;
}

interface ConditionalTabsProps {
  tabs: Tab[];
  activeIndex: number;
  onActiveIndexChange: (index: number) => void;
}

// TODO: Animate line between tab changes
export const ConditionalTabs = ({
  tabs,
  activeIndex,
  onActiveIndexChange,
}: ConditionalTabsProps) => {
  const baseId = useId();

  const tablistRef = useRef<HTMLDivElement>(null);

  // tldraw registers a bubble-phase `touchstart` listener on its container that
  // calls preventDefault to block browser edge-swipe. Near the screen edge that
  // fires a passive-listener warning and can swallow the tap. Stop the native
  // touch event here so it never reaches tldraw's listener
  useEffect(() => {
    const tablist = tablistRef.current;
    if (!tablist) return;

    const fixBubbling = (event: TouchEvent) => event.stopPropagation();
    tablist.addEventListener('touchstart', fixBubbling);
    return () => tablist.removeEventListener('touchstart', fixBubbling);
  }, []);

  const tabId = (index: number) => `${baseId}-tab-${index}`;

  const panelId = (index: number) => `${baseId}-tabpanel-${index}`;

  const activeTab = tabs[activeIndex];

  return (
    <div className={s.container}>
      <div ref={tablistRef} role="tablist" className={s['tabs-container']}>
        {tabs.map((tab, index) => {
          const isActive = index === activeIndex;

          return (
            <button
              key={tab.label}
              className={s.tab}
              type="button"
              role="tab"
              id={tabId(index)}
              aria-controls={panelId(index)}
              aria-selected={isActive}
              data-is-active={isActive}
              // Prevent tldraw from trigger drag event on click
              onPointerDown={(event) => event.stopPropagation()}
              // Prevent tldraw from intercepting pointerup and swallowing the click
              onPointerUp={(event) => event.stopPropagation()}
              onClick={() => onActiveIndexChange(index)}
            >
              <tab.icon className={s.icon} />
              <span>{tab.label}</span>
            </button>
          );
        })}
      </div>

      <AnimatePresence initial={false} mode="wait">
        {activeTab && (
          <m.div
            key={activeTab.label}
            role="tabpanel"
            className={s.panel}
            id={panelId(activeIndex)}
            aria-labelledby={tabId(activeIndex)}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2, ease: 'linear' }}
          >
            {activeTab.children}
          </m.div>
        )}
      </AnimatePresence>
    </div>
  );
};
