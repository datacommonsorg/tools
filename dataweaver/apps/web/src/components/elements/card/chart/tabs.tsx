import type { ComponentPropsWithRef, ComponentType } from 'react';
import s from './tabs.module.scss';

export interface TabItem {
  id: string;
  label: string;
  icon: ComponentType<ComponentPropsWithRef<'svg'>>;
}

interface TabsProps {
  tabs: TabItem[];
  activeTab: string;
  onChange: (id: string) => void;
}

// TODO: Animate line between tab changes
export const Tabs = ({ tabs, activeTab, onChange }: TabsProps) => {
  return (
    <div className={s.container}>
      <div role="tablist" className={s['tabs-container']}>
        {tabs.map((tab) => {
          const isActive = tab.id === activeTab;

          return (
            <button
              key={tab.id}
              className={s.tab}
              type="button"
              role="tab"
              aria-selected={isActive}
              data-is-active={isActive}
              // Prevent tldraw from trigger drag event on click
              onPointerDown={(event) => event.stopPropagation()}
              onClick={() => onChange(tab.id)}
            >
              <tab.icon className={s.icon} />
              <span>{tab.label}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
};
