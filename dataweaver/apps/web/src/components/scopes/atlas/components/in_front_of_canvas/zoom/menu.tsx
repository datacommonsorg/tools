import { EASE_OUT } from '@package/tokens/ts';
import { m } from 'motion/react';
import type { ComponentPropsWithRef, ComponentType } from 'react';
import { type Editor, useEditor } from 'tldraw';
import { IconCmd } from '~/components/primitives/icons/cmd';
import { IconCtrl } from '~/components/primitives/icons/ctrl';
import { IconMinus } from '~/components/primitives/icons/minus';
import { IconPlus } from '~/components/primitives/icons/plus';
import { IconShift } from '~/components/primitives/icons/shift';
import { IS_APPLE } from '~/configs/environment_client';
import s from './menu.module.scss';

type ZoomModifier = 'primary' | 'shift';

type IconComponent = ComponentType<ComponentPropsWithRef<'svg'>>;

interface ZoomAction {
  id: string;
  label: string;
  shortcut: { modifier: ZoomModifier; key: string | IconComponent };
  run(editor: Editor): void;
}

/**
 * List of supported actions in dropdown menu. For the actual shortcut modifiers
 * and keys we're just matching what TLDraw natively supports.
 */
const ZOOM_ACTIONS: readonly ZoomAction[] = [
  {
    id: 'in',
    label: 'Zoom in',
    shortcut: { modifier: 'primary', key: IconPlus },
    run: (editor) => editor.zoomIn(),
  },
  {
    id: 'out',
    label: 'Zoom out',
    shortcut: { modifier: 'primary', key: IconMinus },
    run: (editor) => editor.zoomOut(),
  },
  {
    id: 'reset',
    label: 'Zoom to 100%',
    shortcut: { modifier: 'shift', key: '0' },
    run: (editor) => editor.resetZoom(),
  },
  {
    id: 'fit',
    label: 'Zoom to fit',
    shortcut: { modifier: 'shift', key: '1' },
    run: (editor) => editor.zoomToFit(),
  },
  {
    id: 'selection',
    label: 'Zoom to selection',
    shortcut: { modifier: 'shift', key: '2' },
    run: (editor) => editor.zoomToSelection(),
  },
] as const;

interface ModifierHintProps {
  modifier: ZoomModifier;
}

const ModifierHint = ({ modifier }: ModifierHintProps) => {
  const Icon = modifier === 'shift' ? IconShift : IS_APPLE ? IconCmd : IconCtrl;

  return <Icon className={s['icon-modifier']} />;
};

interface KeyHintProps {
  shortcutKey: string | IconComponent;
}

const KeyHint = ({ shortcutKey: Key }: KeyHintProps) => {
  if (typeof Key === 'string') return Key;

  return <Key className={s['icon-key']} />;
};

interface MenuProps {
  id: string;
  prefersMotion: boolean;
  onClose(): void;
}

export const Menu = ({ id, prefersMotion, onClose }: MenuProps) => {
  const editor = useEditor();

  return (
    <m.dialog
      open
      id={id}
      className={s['menu-container']}
      aria-label="Zoom options"
      // Prevent tldraw from treating menu interactions as canvas gestures
      onPointerDown={(event) => event.stopPropagation()}
      onWheelCapture={(event) => event.stopPropagation()}
      {...(prefersMotion && {
        initial: { opacity: 0, transform: 'translateY(-8px)' },
        animate: { opacity: 1, transform: 'translateY(0px)' },
        exit: { opacity: 0, transform: 'translateY(-8px)' },
        transition: { duration: 0.2, ease: EASE_OUT },
      })}
    >
      <ul className={s['actions-container']}>
        {ZOOM_ACTIONS.map((action) => (
          <li key={action.id}>
            <button
              type="button"
              className={s['button-action']}
              onClick={() => {
                action.run(editor);
                onClose();
              }}
            >
              <span className={s.label}>{action.label}</span>

              <span className={s.shortcut} aria-hidden>
                <ModifierHint modifier={action.shortcut.modifier} />
                <KeyHint shortcutKey={action.shortcut.key} />
              </span>
            </button>
          </li>
        ))}
      </ul>
    </m.dialog>
  );
};
