import s from './controls.module.scss';
import { Export } from './export/export';
import { History } from './history';
import { Zoom } from './zoom/zoom';

/**
 * Editor-bound controls rendered through tldraw's `InFrontOfTheCanvas` slot:
 * the undo / redo history control, the zoom menu and the export menu.
 */
export const Controls = () => {
  return (
    <div className={s.container}>
      <History />
      <Zoom />
      <Export />
    </div>
  );
};
