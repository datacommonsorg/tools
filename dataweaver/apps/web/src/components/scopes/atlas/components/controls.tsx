import { useEditor, useValue } from 'tldraw';
import { Button } from '~/components/elements/button';
import { IconCursor } from '~/components/primitives/icons/cursor';
import { IconExport } from '~/components/primitives/icons/export';
import { IconHand } from '~/components/primitives/icons/hand';
import { IconInsertText } from '~/components/primitives/icons/insert_text';
import { IconMinus } from '~/components/primitives/icons/minus';
import { IconPlus } from '~/components/primitives/icons/plus';
import {
  MAX_ZOOM,
  MIN_ZOOM,
  ZOOM_DISPLAY_RANGE,
} from '~/components/scopes/atlas/config';
import { mapRange } from '~/functions/map_range';
import s from './controls.module.scss';

const TOOLS = {
  select: { label: 'Select', Icon: IconCursor },
  hand: { label: 'Pan', Icon: IconHand },
  text: { label: 'Text', Icon: IconInsertText },
} as const;

type ToolName = keyof typeof TOOLS;

/** Type guard to ensure a given string is a valid ToolName. */
const isToolName = (name: string): name is ToolName => name in TOOLS;

const BUTTON_EXPORT_COLOR_SCHEME = {
  base: 'var(--color-control-surface)',
  'base-hover': 'var(--color-control-surface-hover)',
  content: 'var(--color-control-accent)',
  'content-hover': 'var(--color-control-accent)',
};

const BUTTON_ZOOM_COLOR_SCHEME = {
  base: 'transparent',
  'base-hover': 'var(--color-control-surface-hover)',
  content: 'var(--color-control-accent)',
  'content-hover': 'var(--color-control-accent)',
};

const BUTTON_TOOL_COLOR_SCHEME_SELECTED = {
  base: 'var(--color-control-accent)',
  'base-hover': 'var(--color-control-accent)',
  content: 'var(--color-control-accent-content)',
  'content-hover': 'var(--color-control-accent-content)',
};

const BUTTON_TOOL_COLOR_SCHEME_INACTIVE = {
  base: 'transparent',
  'base-hover': 'var(--color-control-surface-hover)',
  content: 'var(--color-control-content)',
  'content-hover': 'var(--color-control-content)',
};

/**
 * Editor-bound wrapper rendered through tldraw's `InFrontOfTheCanvas` slot so
 * it can read live tool / zoom state via `useEditor`.
 */
export const Controls = () => {
  const editor = useEditor();

  const tool = useValue('tool', () => editor.getCurrentToolId(), [editor]);
  const zoom = useValue('zoom', () => editor.getZoomLevel(), [editor]);

  // Here we map the tldraw tool to one of our supported ones. If it's not found
  // we fallback to default 'select' tool
  const activeToolName: ToolName = isToolName(tool) ? tool : 'select';

  // Rescale the actual zoom from tldraw's enforced min / max (the first and
  // last zoom steps) onto the value we display
  const zoomDisplay = Math.round(
    mapRange(
      zoom,
      MIN_ZOOM,
      MAX_ZOOM,
      ZOOM_DISPLAY_RANGE[0],
      ZOOM_DISPLAY_RANGE[1],
    ),
  );

  return (
    <div className={s.container}>
      <div className={s['controls-container']}>
        <div className={s['zoom-container']} role="toolbar" aria-label="Zoom">
          <Button
            icon={IconPlus}
            size="small"
            aria-label="Zoom in"
            colorScheme={BUTTON_ZOOM_COLOR_SCHEME}
            onClick={() => editor.zoomIn()}
          />

          <span className={s['zoom-value']}>{zoomDisplay}%</span>

          <Button
            icon={IconMinus}
            size="small"
            aria-label="Zoom out"
            colorScheme={BUTTON_ZOOM_COLOR_SCHEME}
            onClick={() => editor.zoomOut()}
          />
        </div>

        <Button
          icon={IconExport}
          size="large"
          className={s['button-export']}
          colorScheme={BUTTON_EXPORT_COLOR_SCHEME}
          // TODO: Support export here
        >
          Export
        </Button>
      </div>

      <div
        className={s['tools-container']}
        role="toolbar"
        aria-orientation="vertical"
        aria-label="Tools"
      >
        {Object.entries(TOOLS).map(([name, tool]) => (
          <Button
            key={name}
            icon={tool.Icon}
            size="large"
            aria-label={tool.label}
            aria-pressed={activeToolName === name}
            colorScheme={
              activeToolName === name
                ? BUTTON_TOOL_COLOR_SCHEME_SELECTED
                : BUTTON_TOOL_COLOR_SCHEME_INACTIVE
            }
            onClick={() => editor.setCurrentTool(name)}
          />
        ))}
      </div>
    </div>
  );
};
