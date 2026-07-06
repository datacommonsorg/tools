import { AnimatePresence } from 'motion/react';
import { useId, useRef } from 'react';
import { useExport } from '~/components/scopes/atlas/export_provider';
import { CARD_DATA_ATTRIBUTE } from '~/components/scopes/atlas/shapes/card';
import { useClickOutside } from '~/hooks/use_click_outside';
import { useFocusTrap } from '~/hooks/use_focus_trap';
import { Control } from './control';
import s from './export.module.scss';
import { Menu } from './menu';

/** Prevent card clicks from closing the export menu. */
const IGNORE_TARGETS = [`[${CARD_DATA_ATTRIBUTE}]`];

export const Export = () => {
  const menuId = useId();

  const { isOpen, toggle, close } = useExport();

  const containerRef = useRef<HTMLDivElement>(null);

  useClickOutside(containerRef, close, {
    isEnabled: isOpen,
    ignoreTargets: IGNORE_TARGETS,
  });

  useFocusTrap(containerRef, { isEnabled: isOpen });

  return (
    <div ref={containerRef} className={s.container}>
      <Control id={menuId} isOpen={isOpen} onToggle={toggle} />

      <AnimatePresence>
        {isOpen && <Menu id={menuId} onClose={close} />}
      </AnimatePresence>
    </div>
  );
};
