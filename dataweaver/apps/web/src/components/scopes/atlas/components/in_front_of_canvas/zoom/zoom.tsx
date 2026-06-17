import { AnimatePresence } from 'motion/react';
import { useId, useRef, useState } from 'react';
import { useClickOutside } from '~/hooks/use_click_outside';
import { useFocusTrap } from '~/hooks/use_focus_trap';
import { useKeydown } from '~/hooks/use_keydown';
import { useMatchMedia } from '~/hooks/use_match_media';
import { Control } from './control';
import { Menu } from './menu';
import s from './zoom.module.scss';

export const Zoom = () => {
  const menuId = useId();

  const containerRef = useRef<HTMLDivElement>(null);

  const [isOpen, setIsOpen] = useState(false);

  const prefersMotion = useMatchMedia('prefers-motion');

  const toggle = () => setIsOpen((isOpen) => !isOpen);

  const close = () => setIsOpen(false);

  useKeydown('Escape', close, { isEnabled: isOpen });

  useClickOutside(containerRef, close, { isEnabled: isOpen });

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
