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

type ToolName = keyof typeof TOOLS;

/** Type guard to ensure a given string is a valid ToolName. */
const isToolName = (name: string): name is ToolName => name in TOOLS;

/**
 * Editor-bound wrapper rendered through tldraw's `InFrontOfTheCanvas` slot so
 * it can read live tool / zoom state via `useEditor`.
 */
export const Tools = () => {
  const editor = useEditor();

  const tool = useValue('tool', () => editor.getCurrentToolId(), [editor]);

  // Here we map the tldraw tool to one of our supported ones. If it's not found
  // we fallback to default 'select' tool
  const activeToolName: ToolName = isToolName(tool) ? tool : 'select';

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
          aria-label={tool.label}
          aria-pressed={activeToolName === name}
          tone={activeToolName === name ? 'accent' : 'subtle'}
          onClick={() => editor.setCurrentTool(name)}
        />
      ))}
    </div>
  );
};
