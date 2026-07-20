import { AnimatePresence } from 'motion/react';
import { useId, useRef, useState } from 'react';
import { useClickOutside } from '~/hooks/use_click_outside';
import { Control } from './control';
import s from './import.module.scss';
import { Menu } from './menu';

export const Import = () => {
  const menuId = useId();

  const containerRef = useRef<HTMLDivElement>(null);

  const [isOpen, setIsOpen] = useState(false);

  const toggle = () => setIsOpen((isOpen) => !isOpen);

  const close = () => setIsOpen(false);

  useClickOutside(containerRef, close, { isEnabled: isOpen });

  return (
    <div ref={containerRef} className={s.container}>
      <Control id={menuId} isOpen={isOpen} onToggle={toggle} />

      <AnimatePresence>
        {isOpen && <Menu id={menuId} onClose={close} />}
      </AnimatePresence>
    </div>
  );
};
