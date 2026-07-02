import { EASE_OUT } from '@package/tokens/ts';
import { AnimatePresence, m } from 'motion/react';
import { useEditor, useValue } from 'tldraw';
import { Button } from '~/components/elements/button';
import { Menu as MenuElement } from '~/components/elements/menu';
import { IconClose } from '~/components/primitives/icons/close';
import s from './menu.module.scss';
import { StatusEmpty } from './status_empty';
import { StatusSelected } from './status_selected';

interface MenuProps {
  id: string;
  onClose(): void;
}

export const Menu = ({ id, onClose }: MenuProps) => {
  const editor = useEditor();

  const totalSelected = useValue('atlas-selected-card-count', () => {
    return editor.getSelectedShapeIds().filter((id) => {
      const shape = editor.getShape(id);
      return shape ? shape.type === 'card' : false;
    }).length;
  }, [editor]);

  const status = totalSelected > 0 ? 'selected' : 'empty';

  return (
    <MenuElement
      id={id}
      className={s.menu}
      aria-label="Export"
      onClose={onClose}
      // Keep canvas gestures from leaking through to tldraw behind the menu
      onPointerDown={(event) => event.stopPropagation()}
      onWheelCapture={(event) => event.stopPropagation()}
      onKeyDown={(event) => event.stopPropagation()}
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
          size="large"
          variant="flat"
          tone="subtle"
          aria-label="Close export"
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
    </MenuElement>
  );
};
