import { AnimatePresence, m } from 'motion/react';
import type { ComponentPropsWithRef, ComponentType, ReactNode } from 'react';
import { useId, useState } from 'react';
import s from './conditional_tabs.module.scss';

interface Tab {
  icon: ComponentType<ComponentPropsWithRef<'svg'>>;

  /** **Note**: Make sure each label is unique as it's used as key. */
  label: string;
  children: ReactNode;
}

interface ConditionalTabsProps {
  tabs: Tab[];
}

// TODO: Animate line between tab changes
export const ConditionalTabs = ({ tabs }: ConditionalTabsProps) => {
  const baseId = useId();

  const [activeIndex, setActiveIndex] = useState(0);

  const tabId = (index: number) => `${baseId}-tab-${index}`;

  const panelId = (index: number) => `${baseId}-tabpanel-${index}`;

  const activeTab = tabs[activeIndex];

  return (
    <>
      <div role="tablist" className={s['tabs-container']}>
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
              onClick={() => setActiveIndex(index)}
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
    </>
  );
};
