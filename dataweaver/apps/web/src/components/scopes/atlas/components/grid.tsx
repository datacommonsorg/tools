import { useEditor, useValue } from 'tldraw';
import s from './grid.module.scss';

/**
 * Dot grid that tracks the camera. TLDraw transforms only its inner canvas
 * layer, so the background sits in screen space: dots pan with the camera
 * ('x * z', 'y * z') but keep a fixed screen size (no zoom scaling).
 */
export const Grid = () => {
  const editor = useEditor();

  const { x, y, z } = useValue('camera', () => editor.getCamera(), [editor]);

  return (
    <div
      className={s.grid}
      style={{ backgroundPosition: `${x * z}px ${y * z}px` }}
    />
  );
};
