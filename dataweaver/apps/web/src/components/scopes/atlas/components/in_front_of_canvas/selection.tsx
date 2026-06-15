import { EASE_LINEAR } from '@package/tokens/ts';
import { AnimatePresence, m } from 'motion/react';
import { useCallback, useRef } from 'react';
import { useEditor, useQuickReactor, useValue } from 'tldraw';
import { Button } from '~/components/elements/button';
import { toast } from '~/components/foundations/toaster/store';
import { IconBarChart } from '~/components/primitives/icons/bar_chart';
import { IconDelete } from '~/components/primitives/icons/delete';
import { IconExport } from '~/components/primitives/icons/export';
import { useExportActions } from '~/components/scopes/atlas/export_provider';
import { useMatchMedia } from '~/hooks/use_match_media';
import s from './selection.module.scss';

/** Screen-space margin the selection box extends past the cards, in pixels. */
const INSET_SIDES_AND_BOTTOM = 16;

/** Larger top margin, leaving room to seat the action panel above the cards. */
const INSET_TOP = 60;

const BUTTON_COLOR_SCHEME = {
  base: 'transparent',
  'base-hover': 'var(--color-card-base)',
  content: 'var(--color-card-base)',
  'content-hover': 'var(--color-card-base-selected)',
};

export const Selection = () => {
  const editor = useEditor();
  const { open: openExport } = useExportActions();

  const containerRef = useRef<HTMLDivElement>(null);

  const prefersMotion = useMatchMedia('prefers-motion');

  const hasMultipleSelected = useValue('multi-selection-active', () => {
    return editor.getSelectedShapeIds().length > 1;
  }, [editor]);

  const position = useCallback(() => {
    const bounds = editor.getSelectionPageBounds();
    const { z: zoom } = editor.getCamera();

    const container = containerRef.current;
    if (!container || !bounds) return;

    const origin = editor.pageToViewport({ x: bounds.x, y: bounds.y });
    const left = origin.x - INSET_SIDES_AND_BOTTOM;
    const top = origin.y - INSET_TOP;
    const width = bounds.width * zoom + INSET_SIDES_AND_BOTTOM * 2;
    const height = bounds.height * zoom + INSET_TOP + INSET_SIDES_AND_BOTTOM;

    container.style.transform = `translate(${left}px, ${top}px)`;
    container.style.width = `${width}px`;
    container.style.height = `${height}px`;
  }, [editor]);

  // Keep the box tracking the canvas while it's mounted
  useQuickReactor('position multi-selection', position, [position]);

  // On mount; set container + position to ensure it's always correctly placed.
  const setContainer = useCallback(
    (container: HTMLDivElement | null) => {
      containerRef.current = container;
      position();
    },
    [position],
  );

  return (
    <AnimatePresence>
      {hasMultipleSelected && (
        <m.div
          ref={setContainer}
          className={s.container}
          {...(prefersMotion && {
            initial: { opacity: 0 },
            animate: { opacity: 1 },
            exit: { opacity: 0 },
            transition: { duration: 0.1, ease: EASE_LINEAR },
          })}
        >
          <div
            className={s['actions-container']}
            role="toolbar"
            aria-label="Selection actions"
          >
            <Button
              icon={IconBarChart}
              size="large"
              aria-label="View chart"
              colorScheme={BUTTON_COLOR_SCHEME}
              // Prevent tldraw from treating the press as a canvas gesture
              onPointerDown={(event) => event.stopPropagation()}
              // TODO: Support chart options here
              onClick={() =>
                toast(
                  'Selection chart options not supported yet',
                  'This feature will be coming in a future release. Stay tuned!',
                )
              }
            />
            <Button
              icon={IconExport}
              size="large"
              aria-label="Export"
              colorScheme={BUTTON_COLOR_SCHEME}
              onPointerDown={(event) => event.stopPropagation()}
              onClick={openExport}
            />
            <Button
              icon={IconDelete}
              size="large"
              aria-label="Delete"
              colorScheme={BUTTON_COLOR_SCHEME}
              onPointerDown={(event) => event.stopPropagation()}
              onClick={() => editor.deleteShapes(editor.getSelectedShapeIds())}
            />
          </div>
        </m.div>
      )}
    </AnimatePresence>
  );
};
