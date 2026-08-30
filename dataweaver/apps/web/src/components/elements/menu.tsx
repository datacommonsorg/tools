import { EASE_OUT } from '@package/tokens/ts';
import { m } from 'motion/react';
import { type ComponentProps, useLayoutEffect, useRef } from 'react';
import { mergeClassNames } from '~/functions/merge_class_names';
import { useFocusTrap } from '~/hooks/use_focus_trap';
import { useKeydown } from '~/hooks/use_keydown';
import { useMatchMedia } from '~/hooks/use_match_media';
import s from './menu.module.scss';

/** Minimum gap to keep between the menu and the edge of the viewport. */
const VIEWPORT_EDGE_MARGIN = 15;

interface MenuProps
  extends DistributiveOmit<ComponentProps<typeof m.dialog>, 'ref'> {
  onClose: () => void;
}

export const Menu = (props: MenuProps) => {
  const prefersMotion = useMatchMedia('prefers-motion', { defaultValue: null });

  return (
    prefersMotion !== null && (
      <MenuWithPrefersMotion {...props} prefersMotion={prefersMotion} />
    )
  );
};

interface MenuWithPrefersMotionProps extends MenuProps {
  prefersMotion: boolean;
}

const MenuWithPrefersMotion = ({
  className,
  prefersMotion,
  children,
  onClose,
  ...rest
}: MenuWithPrefersMotionProps) => {
  const containerRef = useRef<HTMLDialogElement>(null);

  useKeydown('Escape', onClose);

  useFocusTrap(containerRef);

  // The menu is anchored to its trigger button, not the viewport, so on
  // narrow screens (or once controls wrap onto a second row) it can land
  // off-screen or too tall for the remaining space. Clamp both using its
  // actual measured position.
  useLayoutEffect(() => {
    const el = containerRef.current;
    const parent = el?.offsetParent;
    if (!el || !(parent instanceof HTMLElement)) return;

    const clamp = () => {
      el.style.removeProperty('left');
      el.style.removeProperty('right');
      el.style.removeProperty('max-height');

      const rect = el.getBoundingClientRect();
      const parentRect = parent.getBoundingClientRect();

      if (rect.left < VIEWPORT_EDGE_MARGIN) {
        el.style.left = `${VIEWPORT_EDGE_MARGIN - parentRect.left}px`;
        el.style.right = 'auto';
      } else if (rect.right > window.innerWidth - VIEWPORT_EDGE_MARGIN) {
        el.style.right = `${parentRect.right - (window.innerWidth - VIEWPORT_EDGE_MARGIN)}px`;
        el.style.left = 'auto';
      }

      el.style.maxHeight = `${window.innerHeight - rect.top - VIEWPORT_EDGE_MARGIN}px`;
    };

    clamp();
    window.addEventListener('resize', clamp);
    return () => window.removeEventListener('resize', clamp);
  }, []);

  return (
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
      <div className={s['scroll-container']}>{children}</div>
    </m.dialog>
  );
};
