'use client';

import { EASE_LINEAR } from '@package/tokens/ts';
import { m } from 'motion/react';
import type { ComponentPropsWithRef, ComponentType } from 'react';
import { useRef, useState } from 'react';
import { Button } from '~/components/elements/button';
import { Radio } from '~/components/elements/radio';
import { IconBarChartHorizontal } from '~/components/primitives/icons/bar_chart_horizontal';
import { IconBarChartVertical } from '~/components/primitives/icons/bar_chart_vertical';
import { IconLineGraphDouble } from '~/components/primitives/icons/line_graph_double';
import { ScreenReaderOnly } from '~/components/primitives/screen_reader';
import { useClickOutside } from '~/hooks/use_click_outside';
import { useFocusTrap } from '~/hooks/use_focus_trap';
import { useKeydown } from '~/hooks/use_keydown';
import s from './menu_chart_options.module.scss';

export type ChartStyle = 'bar-vertical' | 'bar-horizontal' | 'line';

interface ChartStyleOption {
  key: ChartStyle;
  label: string;
  icon: ComponentType<ComponentPropsWithRef<'svg'>>;
}

const CHART_STYLE_OPTIONS: ChartStyleOption[] = [
  {
    key: 'bar-vertical',
    label: 'Bar chart vertical',
    icon: IconBarChartVertical,
  },
  {
    key: 'bar-horizontal',
    label: 'Bar chart horizontal',
    icon: IconBarChartHorizontal,
  },
  {
    key: 'line',
    label: 'Line chart',
    icon: IconLineGraphDouble,
  },
] as const;

interface MenuChartOptionsProps {
  value: ChartStyle;
  onConfirmSelectionChange: (style: ChartStyle) => void;
  onClose: () => void;
}

export const MenuChartOptions = ({
  value,
  onClose,
  onConfirmSelectionChange,
}: MenuChartOptionsProps) => {
  const contentContainerRef = useRef<HTMLElement>(null);

  const [selectedValue, setSelectedValue] = useState<ChartStyle>(value);

  useClickOutside(contentContainerRef, onClose);

  useKeydown('Escape', onClose);

  // TODO: For now this doesn't seem to really work due to TLDraw consuming
  // tab events. Review focus trap implementation once we review how TLDraw
  // handles focus and keyboard events in general, and adjust as needed
  useFocusTrap(contentContainerRef);

  return (
    <m.dialog
      className={s.container}
      open
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.1, ease: EASE_LINEAR }}
      onPointerDown={(event) => event.stopPropagation()}
    >
      <span className={s.backdrop} />

      <section ref={contentContainerRef} className={s['content-container']}>
        <h2 className={s.title}>Chart options</h2>

        <fieldset className={s['options-container']}>
          <ScreenReaderOnly element="legend">
            Choose a chart style
          </ScreenReaderOnly>

          <ul>
            {CHART_STYLE_OPTIONS.map((option) => (
              <li key={option.key}>
                <Radio
                  className={s['option-container']}
                  name="chart-style"
                  value={option.key}
                  checked={selectedValue === option.key}
                  onChange={() => setSelectedValue(option.key)}
                >
                  <option.icon className={s['option-icon']} />
                  <span className={s['option-label']}>{option.label}</span>
                </Radio>
              </li>
            ))}
          </ul>
        </fieldset>

        <div className={s['actions-container']}>
          <Button
            size="medium"
            variant="flat"
            tone="subtle-highlight"
            onClick={onClose}
          >
            Cancel
          </Button>

          <Button
            className={s['button-update']}
            size="medium"
            variant="border"
            tone="subtle-highlight"
            onClick={() => onConfirmSelectionChange(selectedValue)}
          >
            Update chart style
          </Button>
        </div>
      </section>
    </m.dialog>
  );
};
