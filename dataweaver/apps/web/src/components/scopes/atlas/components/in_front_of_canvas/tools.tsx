import { useEditor, useValue } from 'tldraw';
import { Button } from '~/components/elements/button';
import { IconCursor } from '~/components/primitives/icons/cursor';
import { IconHand } from '~/components/primitives/icons/hand';
import { IconInsertText } from '~/components/primitives/icons/insert_text';
import s from './tools.module.scss';

const TOOLS = {
  select: { label: 'Select', Icon: IconCursor },
  hand: { label: 'Pan', Icon: IconHand },
  text: { label: 'Text', Icon: IconInsertText },
} as const;

/**
 * Editor-bound wrapper rendered through tldraw's `InFrontOfTheCanvas` slot so
 * it can read live tool / zoom state via `useEditor`.
 */
export const Tools = () => {
  const editor = useEditor();

  const activeToolName = useValue('tool', () => {
    return editor.getCurrentToolId();
  }, [editor]);

  return (
    <div
      className={s.container}
      role="toolbar"
      aria-orientation="vertical"
      aria-label="Tools"
    >
      {Object.entries(TOOLS).map(([name, tool]) => (
        <Button
          key={name}
          icon={tool.Icon}
          size="large"
          variant="flat"
          tone="subtle"
          isActive={activeToolName === name}
          aria-label={tool.label}
          aria-pressed={activeToolName === name}
          onClick={() => editor.setCurrentTool(name)}
        />
      ))}
    </div>
  );
};
