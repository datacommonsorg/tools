import { Portal } from '~/components/primitives/portal';
import { Controls } from './controls';
import s from './index.module.scss';
import { Selection } from './selection/selection';
import { Tools } from './tools';

export const InFrontOfTheCanvas = () => {
  // These elements read live editor state via 'useEditor', so they must render
  // inside tldraw's React tree — but tldraw's container owns a stacking context
  // that traps them below app content (page_home). The 'Portal' lifts their DOM
  // to above that content while keeping them in the editor's React tree
  return (
    <Portal className={s.container}>
      <Controls />
      <Tools />
      <Selection />
    </Portal>
  );
};
