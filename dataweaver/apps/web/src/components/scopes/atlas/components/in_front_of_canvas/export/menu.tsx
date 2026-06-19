import { EASE_OUT } from '@package/tokens/ts';
import { AnimatePresence, m } from 'motion/react';
import { useEditor, useValue } from 'tldraw';
import { Button } from '~/components/elements/button';
import { IconClose } from '~/components/primitives/icons/close';
import s from './menu.module.scss';
import { StatusEmpty } from './status_empty';
import { StatusSelected } from './status_selected';

const BUTTON_CLOSE_COLOR_SCHEME = {
  base: 'transparent',
  'base-hover': 'var(--color-control-surface-hover)',
  content: 'var(--color-control-content)',
  'content-hover': 'var(--color-control-content)',
};

interface MenuProps {
  id: string;
  prefersMotion: boolean;
  onClose(): void;
}

export const Menu = ({ id, prefersMotion, onClose }: MenuProps) => {
  const editor = useEditor();

  const totalSelected = useValue('atlas-selected-card-count', () => {
    return editor.getSelectedShapeIds().filter((id) => {
      const shape = editor.getShape(id);
      return shape ? shape.type === 'card' : false;
    }).length;
  }, [editor]);

  const status = totalSelected > 0 ? 'selected' : 'empty';

  return (
    <m.dialog
      open
      id={id}
      className={s.container}
      aria-modal="false"
      aria-label="Export"
      // Prevent tldraw from treating panel interactions as canvas gestures
      onPointerDown={(event) => event.stopPropagation()}
      onWheelCapture={(event) => event.stopPropagation()}
      onKeyDown={(event) => event.stopPropagation()}
      {...(prefersMotion && {
        initial: { opacity: 0, transform: 'translateY(-8px)' },
        animate: { opacity: 1, transform: 'translateY(0px)' },
        exit: { opacity: 0, transform: 'translateY(-8px)' },
        transition: { duration: 0.3, ease: EASE_OUT },
      })}
    >
      <header className={s['header-container']}>
        <h2 className={s.title}>
          Export
          <AnimatePresence initial={false}>
            {status === 'selected' && (
              <m.span
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                // Delay here ensures this matches status mode wait reveal
                transition={{ duration: 0.2, delay: 0.2, ease: EASE_OUT }}
              >
                {` (${totalSelected} selected)`}
              </m.span>
            )}
          </AnimatePresence>
        </h2>

        <Button
          icon={IconClose}
          className={s['button-close']}
          size="medium"
          aria-label="Close export"
          colorScheme={BUTTON_CLOSE_COLOR_SCHEME}
          onClick={onClose}
        />
      </header>

      <AnimatePresence mode="wait" initial={false}>
        <m.div
          key={status}
          className={s['content-container']}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.2, ease: EASE_OUT }}
        >
          {status === 'empty' ? <StatusEmpty /> : <StatusSelected />}
        </m.div>
      </AnimatePresence>
    </m.dialog>
  );
};
