import s from './controls.module.scss';
import { Export } from './export/export';
import { Zoom } from './zoom/zoom';

/**
 * Editor-bound controls rendered through tldraw's `InFrontOfTheCanvas` slot:
 * the zoom menu and the export menu, each owning its own trigger + popover.
 */
export const Controls = () => {
  return (
    <div className={s.container}>
      <Zoom />
      <Export />
    </div>
  );
};
