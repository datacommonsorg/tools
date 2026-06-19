import { EASE_OUT } from '@package/tokens/ts';
import { m } from 'motion/react';
import { type ComponentProps, useRef } from 'react';
import { mergeClassNames } from '~/functions/merge_class_names';
import { useFocusTrap } from '~/hooks/use_focus_trap';
import { useKeydown } from '~/hooks/use_keydown';
import { useMatchMedia } from '~/hooks/use_match_media';
import s from './menu.module.scss';

interface MenuProps
  extends DistributiveOmit<ComponentProps<typeof m.dialog>, 'ref'> {
  onClose: () => void;
}

export const Menu = ({ className, children, onClose, ...rest }: MenuProps) => {
  const containerRef = useRef<HTMLDialogElement>(null);

  const prefersMotion = useMatchMedia('prefers-motion', { defaultValue: null });

  useKeydown('Escape', onClose);

  // TODO: For now this doesn't seem to really work due to TLDraw consuming
  // tab events. Review focus trap implementation once we review how TLDraw
  // handles focus and keyboard events in general, and adjust as needed
  useFocusTrap(containerRef);

  return (
    prefersMotion !== null && (
      <m.dialog
        {...rest}
        ref={containerRef}
        className={mergeClassNames(s.container, className)}
        open
        initial={{
          opacity: 0,
          ...(prefersMotion && { transform: 'translateY(-8px)' }),
        }}
        animate={{
          opacity: 1,
          ...(prefersMotion && { transform: 'translateY(0px)' }),
        }}
        exit={{
          opacity: 0,
          ...(prefersMotion && { transform: 'translateY(-8px)' }),
        }}
        transition={{ duration: 0.2, ease: EASE_OUT }}
      >
        {children}
      </m.dialog>
    )
  );
};
