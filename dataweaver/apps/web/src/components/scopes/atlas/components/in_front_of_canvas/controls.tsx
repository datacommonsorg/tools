import { useEditor, useValue } from 'tldraw';
import { Button } from '~/components/elements/button';
import { IconExport } from '~/components/primitives/icons/export';
import { IconMinus } from '~/components/primitives/icons/minus';
import { IconPlus } from '~/components/primitives/icons/plus';
import {
  MAX_ZOOM,
  MIN_ZOOM,
  ZOOM_DISPLAY_RANGE,
} from '~/components/scopes/atlas/config';
import { useExport } from '~/components/scopes/atlas/export_provider';
import { mapRange } from '~/functions/map_range';
import s from './controls.module.scss';

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

/**
 * Editor-bound wrapper rendered through tldraw's `InFrontOfTheCanvas` slot so
 * it can read live tool / zoom state via `useEditor`.
 */
export const Controls = () => {
  const editor = useEditor();

  const { isOpen, toggle } = useExport();

  const zoom = useValue('zoom', () => editor.getZoomLevel(), [editor]);

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
        aria-haspopup="dialog"
        aria-expanded={isOpen}
        onClick={toggle}
      >
        Export
      </Button>
    </div>
  );
};
