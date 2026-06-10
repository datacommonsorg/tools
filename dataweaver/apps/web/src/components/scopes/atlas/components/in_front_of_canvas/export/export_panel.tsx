import { EASE_OUT } from '@package/tokens/ts';
import { AnimatePresence, m } from 'motion/react';
import { useEditor, useValue } from 'tldraw';
import { Button } from '~/components/elements/button';
import { IconClose } from '~/components/primitives/icons/close';
import { IconSelect } from '~/components/primitives/icons/select';
import { IconShapes } from '~/components/primitives/icons/shapes';
import { useMatchMedia } from '~/hooks/use_match_media';
import s from './export_panel.module.scss';
import { useExport } from './export_provider';

/** The available export formats shown in the panel's options grid. */
const EXPORT_OPTIONS = [
  {
    title: 'API Request Code',
    description:
      'Your JSON code will appear here once you add content to your canvas.',
  },
  {
    title: 'CSV',
    description:
      "You'll get a separate file for every card that contains data.",
  },
  {
    title: 'AI Narrative',
    description: 'Gemini will summarize your canvas into a narrative.',
  },
  {
    title: 'AI Infographic',
    description: 'Gemini can generate a visual infographic from your canvas.',
  },
  {
    title: 'SVG',
    description:
      "You'll receive a separated vector svg file for each of your selected cards.",
  },
  {
    title: 'PNG',
    description:
      "You'll receive a separated raster png file for each of your selected cards.",
  },
] as const;

export const ExportPanel = () => {
  const editor = useEditor();

  const { isOpen, close } = useExport();

  const prefersMotion = useMatchMedia('prefers-motion');

  const cardCount = useValue('atlas-card-count', () => {
    return editor
      .getCurrentPageShapes()
      .filter((shape) => shape.type === 'card').length;
  }, [editor]);

  const selectedCount = useValue('atlas-selected-card-count', () => {
    return editor.getSelectedShapes().filter((shape) => shape.type === 'card')
      .length;
  }, [editor]);

  const status =
    cardCount === 0 ? 'empty' : selectedCount === 0 ? 'none-selected' : 'ready';

  return (
    <AnimatePresence>
      {isOpen && (
        <m.section
          className={s.container}
          role="dialog"
          aria-modal="false"
          aria-label="Export"
          // Prevent tldraw from treating panel interactions as canvas gestures
          onPointerDown={(event) => event.stopPropagation()}
          onWheelCapture={(event) => event.stopPropagation()}
          {...(prefersMotion && {
            initial: { opacity: 0, transform: 'translateY(-8px)' },
            animate: { opacity: 1, transform: 'translateY(0px)' },
            exit: { opacity: 0, transform: 'translateY(-8px)' },
            transition: { duration: 0.3, ease: EASE_OUT },
          })}
        >
          <header className={s['header-container']}>
            <h2 className={s.title}>Export</h2>

            <Button
              icon={IconClose}
              size="small"
              aria-label="Close export"
              colorScheme={{
                base: 'transparent',
                'base-hover': 'var(--color-control-surface-hover)',
                content: 'var(--color-control-content)',
                'content-hover': 'var(--color-control-content)',
              }}
              onClick={close}
            />
          </header>

          <div className={s['statuses-container']} role="status">
            <AnimatePresence mode="wait">
              <m.div
                key={status}
                className={s['status-container']}
                {...(prefersMotion && {
                  initial: { opacity: 0 },
                  animate: { opacity: 1 },
                  exit: { opacity: 0 },
                  transition: { duration: 0.2, ease: EASE_OUT },
                })}
              >
                {status === 'empty' && (
                  <>
                    <IconShapes className={s['status-icon']} />
                    <p className={s['status-title']}>
                      Create a prompt to begin
                    </p>
                    <p className={s['status-description']}>
                      Once you have data to export, come back to this window.
                    </p>
                  </>
                )}

                {status === 'none-selected' && (
                  <>
                    <IconSelect className={s['status-icon']} />
                    <p className={s['status-title']}>No cards selected</p>
                    <p className={s['status-description']}>
                      Please select 1 or more cards to see export options.
                    </p>
                    <button
                      type="button"
                      className={s['status-button-select-all']}
                      onClick={() => editor.selectAll()}
                    >
                      <span className={s['select-all-label']}>Select All</span>
                      <span className={s['select-all-keys']}>CMD + A</span>
                    </button>
                  </>
                )}

                {status === 'ready' && (
                  <>
                    <IconShapes className={s['status-icon']} />
                    <p className={s['status-title']}>
                      {selectedCount} {selectedCount === 1 ? 'card ' : 'cards '}
                      selected
                    </p>
                    <p className={s['status-description']}>
                      Choose a format below to export your selection.
                    </p>
                  </>
                )}
              </m.div>
            </AnimatePresence>
          </div>

          <section
            className={s['content-container']}
            aria-label="Export options"
          >
            <h3 className={s['options-title']}>Export options</h3>

            <ul className={s['options-container']}>
              {EXPORT_OPTIONS.map((option) => (
                <li key={option.title} className={s['option-container']}>
                  <h4 className={s['option-title']}>{option.title}</h4>
                  <p className={s['option-description']}>
                    {option.description}
                  </p>
                </li>
              ))}
            </ul>
          </section>
        </m.section>
      )}
    </AnimatePresence>
  );
};
