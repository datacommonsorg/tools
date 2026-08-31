import { useEditor, useValue } from 'tldraw';
import { Portal } from '~/components/primitives/portal';
import s from './index.module.scss';
import { Selection } from './selection/selection';

export const OnTheCanvas = () => {
  const editor = useEditor();
  const hasMultipleSelected = useValue(
    'multi-selection-active',
    () => editor.getSelectedShapeIds().length > 1,
    [editor],
  );

  if (!hasMultipleSelected) return null;

  return (
    <Portal className={s.container}>
      <Selection />
    </Portal>
  );
};
