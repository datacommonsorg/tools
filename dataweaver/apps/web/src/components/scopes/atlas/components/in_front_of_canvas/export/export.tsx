import { AnimatePresence } from 'motion/react';
import { useId, useRef } from 'react';
import { useExport } from '~/components/scopes/atlas/export_provider';
import { CARD_DATA_ATTRIBUTE } from '~/components/scopes/atlas/shapes/card';
import { useClickOutside } from '~/hooks/use_click_outside';
import { useFocusTrap } from '~/hooks/use_focus_trap';
import { useKeydown } from '~/hooks/use_keydown';
import { useMatchMedia } from '~/hooks/use_match_media';
import { Control } from './control';
import s from './export.module.scss';
import { Menu } from './menu';

/** Prevent card clicks from closing the export menu. */
const IGNORE_TARGETS = [`[${CARD_DATA_ATTRIBUTE}]`];

export const Export = () => {
  const menuId = useId();

  const { isOpen, toggle, close } = useExport();

  const containerRef = useRef<HTMLDivElement>(null);

  const prefersMotion = useMatchMedia('prefers-motion');

  useKeydown('Escape', close, { isEnabled: isOpen });

  useClickOutside(containerRef, close, {
    isEnabled: isOpen,
    ignoreTargets: IGNORE_TARGETS,
  });

  // TODO: For now this doesn't seem to really work due to TLDraw consuming
  // tab events. Review focus trap implementation once we review how TLDraw
  // handles focus and keyboard events in general, and adjust as needed
  useFocusTrap(containerRef, { isEnabled: isOpen });

  return (
    <div ref={containerRef} className={s.container}>
      <Control id={menuId} isOpen={isOpen} onToggle={toggle} />

      <AnimatePresence>
        {isOpen && (
          <Menu id={menuId} prefersMotion={prefersMotion} onClose={close} />
        )}
      </AnimatePresence>
    </div>
  );
};
