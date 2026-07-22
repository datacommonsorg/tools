import { useEditor, useValue } from 'tldraw';
import { Button } from '~/components/elements/button';
import { Radio } from '~/components/elements/radio';
import { IconSelect } from '~/components/primitives/icons/select';
import { IconShapes } from '~/components/primitives/icons/shapes';
import {
  EXPORT_OPTION_CANVAS,
  EXPORT_OPTIONS,
} from '~/components/scopes/atlas/components/in_front_of_canvas/export/options';
import { IS_APPLE } from '~/configs/environment_client';
import { exportState } from '~/store/serialization';
import { Card } from './card';
import s from './status_empty.module.scss';

export const StatusEmpty = () => {
  const editor = useEditor();

  const totalCards = useValue('atlas-card-count', () => {
    return editor
      .getCurrentPageShapes()
      .filter((shape) => shape.type === 'card').length;
  }, [editor]);

  const selectAllCards = () => {
    const cardIds = editor
      .getCurrentPageShapes()
      .filter((shape) => shape.type === 'card')
      .map((shape) => shape.id);
    editor.select(...cardIds);
  };

  return (
    <>
      {totalCards === 0 ? (
        <Card
          icon={IconShapes}
          title="No active cards"
          description="Ask a question to generate charts and structured data on the canvas. Once cards are added, select items to export."
        />
      ) : (
        <Card
          icon={IconSelect}
          title="Enable"
          description="Please select 1 or more cards to enable export options."
          includeMaxWidth
        >
          <button
            type="button"
            className={s['button-select-all']}
            onClick={selectAllCards}
          >
            <span className={s['select-all-label']}>Select All</span>
            <span className={s['select-all-keys']}>
              {IS_APPLE ? 'Cmd + A' : 'Ctrl + A'}
            </span>
          </button>
        </Card>
      )}

      <section className={s['preview-container']} aria-label="Export options">
        <h3 className={s['preview-title']}>Export options</h3>

        <ul className={s['options-container']}>
          {EXPORT_OPTIONS.map((option) => (
            <li
              key={option.title}
              className={s['option-container']}
              data-has-max-width
            >
              <h4 className={s['option-title']}>{option.title}</h4>
              <p className={s['option-description']}>{option.description}</p>
            </li>
          ))}
        </ul>
      </section>

      <section className={s['canvas-container']} aria-label="Export canvas">
        {totalCards === 0 ? (
          <div className={s['option-container']}>
            <h3 className={s['option-title']}>Export canvas</h3>
            <p className={s['option-description']}>
              {EXPORT_OPTION_CANVAS.description}
            </p>
          </div>
        ) : (
          <>
            <Radio
              name="export-format"
              value={EXPORT_OPTION_CANVAS.key}
              // In this state we have cards but none are selected so given this
              // is only option available we can show it as selected by default
              checked
              readOnly
            >
              <span className={s['option-container']}>
                <span className={s['option-title']}>
                  {EXPORT_OPTION_CANVAS.title}
                </span>
                <span className={s['option-description']}>
                  {EXPORT_OPTION_CANVAS.description}
                </span>
              </span>
            </Radio>

            <Button
              className={s['button-canvas']}
              size="large"
              variant="border"
              tone="subtle-highlight"
              icon={EXPORT_OPTION_CANVAS.icon}
              onClick={exportState}
            >
              {EXPORT_OPTION_CANVAS.action}
            </Button>
          </>
        )}
      </section>
    </>
  );
};
