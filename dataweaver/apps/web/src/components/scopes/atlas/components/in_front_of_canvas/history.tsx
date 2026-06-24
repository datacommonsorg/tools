import { useEditor, useValue } from 'tldraw';
import { Button } from '~/components/elements/button';
import { IconRedo } from '~/components/primitives/icons/redo';
import { IconUndo } from '~/components/primitives/icons/undo';
import s from './history.module.scss';

/** Editor-bound undo / redo control. */
export const History = () => {
  const editor = useEditor();

  const canUndo = useValue('canUndo', () => editor.getCanUndo(), [editor]);
  const canRedo = useValue('canRedo', () => editor.getCanRedo(), [editor]);

  return (
    <div className={s.container} role="toolbar" aria-label="History">
      <Button
        icon={IconUndo}
        size="medium"
        variant="flat"
        tone="subtle-highlight"
        aria-label="Undo"
        isDisabled={!canUndo}
        onClick={() => editor.undo()}
      />

      <span className={s.divider} aria-hidden="true" />

      <Button
        icon={IconRedo}
        size="medium"
        variant="flat"
        tone="subtle-highlight"
        aria-label="Redo"
        isDisabled={!canRedo}
        onClick={() => editor.redo()}
      />
    </div>
  );
};
