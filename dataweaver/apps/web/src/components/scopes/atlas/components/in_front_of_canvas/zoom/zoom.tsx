import { AnimatePresence } from 'motion/react';
import { useId, useRef, useState } from 'react';
import { useClickOutside } from '~/hooks/use_click_outside';
import { useFocusTrap } from '~/hooks/use_focus_trap';
import { Control } from './control';
import { Menu } from './menu';
import s from './zoom.module.scss';

export const Zoom = () => {
  const menuId = useId();

  const containerRef = useRef<HTMLDivElement>(null);

  const [isOpen, setIsOpen] = useState(false);

  const toggle = () => setIsOpen((isOpen) => !isOpen);

  const close = () => setIsOpen(false);

  useClickOutside(containerRef, close, { isEnabled: isOpen });

  // TODO: For now this doesn't seem to really work due to TLDraw consuming
  // tab events. Review focus trap implementation once we review how TLDraw
  // handles focus and keyboard events in general, and adjust as needed
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
