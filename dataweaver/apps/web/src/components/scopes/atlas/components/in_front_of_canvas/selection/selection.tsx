import { EASE_LINEAR } from '@package/tokens/ts';
import { AnimatePresence, m } from 'motion/react';
import { useEditor } from 'tldraw';
import { Button } from '~/components/elements/button';
import { IconDelete } from '~/components/primitives/icons/delete';
import { IconExport } from '~/components/primitives/icons/export';
import { useExportActions } from '~/components/scopes/atlas/export_provider';
import s from './selection.module.scss';
import { useSelectionDragHandle } from './use_selection_drag_handle';
import { useSelectionPosition } from './use_selection_position';

export const Selection = () => {
  const editor = useEditor();
  const { open: openExport } = useExportActions();

  const { hasMultipleSelected, setContainer } = useSelectionPosition();

  const startDragging = useSelectionDragHandle();

  return (
    <AnimatePresence>
      {hasMultipleSelected && (
        <m.div
          ref={setContainer}
          className={s.container}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.1, ease: EASE_LINEAR }}
        >
          <div
            className={s['actions-container']}
            role="toolbar"
            aria-label="Selection actions"
            onPointerDown={startDragging}
          >
            <Button
              icon={IconExport}
              size="large"
              variant="flat"
              tone="card-action"
              aria-label="Export"
              onPointerDown={(event) => event.stopPropagation()}
              onClick={openExport}
            />
            <Button
              icon={IconDelete}
              size="large"
              variant="flat"
              tone="card-action"
              aria-label="Delete"
              onPointerDown={(event) => event.stopPropagation()}
              onClick={() => editor.deleteShapes(editor.getSelectedShapeIds())}
            />
          </div>
        </m.div>
      )}
    </AnimatePresence>
  );
};
