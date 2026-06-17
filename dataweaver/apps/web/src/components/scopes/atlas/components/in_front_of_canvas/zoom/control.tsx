import { useEditor, useValue } from 'tldraw';
import { Button } from '~/components/elements/button';
import { IconMinus } from '~/components/primitives/icons/minus';
import { IconPlus } from '~/components/primitives/icons/plus';
import {
  MAX_ZOOM,
  MIN_ZOOM,
  ZOOM_DISPLAY_RANGE,
} from '~/components/scopes/atlas/config';
import { mapRange } from '~/functions/map_range';
import s from './control.module.scss';

const BUTTON_ZOOM_COLOR_SCHEME = {
  base: 'transparent',
  'base-hover': 'var(--color-control-surface-hover)',
  content: 'var(--color-control-accent)',
  'content-hover': 'var(--color-control-accent)',
};

interface ControlProps {
  id: string;
  isOpen: boolean;
  onToggle(): void;
}

export const Control = ({ id, isOpen, onToggle }: ControlProps) => {
  const editor = useEditor();

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
    <div className={s.container} role="toolbar" aria-label="Zoom">
      <Button
        icon={IconPlus}
        size="small"
        aria-label="Zoom in"
        colorScheme={BUTTON_ZOOM_COLOR_SCHEME}
        onClick={() => editor.zoomIn()}
      />

      <button
        className={s['button-value']}
        type="button"
        aria-label={`Zoom options (${zoomDisplay}%)`}
        aria-haspopup="true"
        aria-expanded={isOpen}
        aria-controls={id}
        onClick={onToggle}
      >
        {zoomDisplay}%
      </button>

      <Button
        icon={IconMinus}
        size="small"
        aria-label="Zoom out"
        colorScheme={BUTTON_ZOOM_COLOR_SCHEME}
        onClick={() => editor.zoomOut()}
      />
    </div>
  );
};
