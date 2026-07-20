import { useState } from 'react';
import { Button } from '~/components/elements/button';
import { Radio } from '~/components/elements/radio';
import { toast } from '~/components/foundations/toaster/store';
import { ScreenReaderOnly } from '~/components/primitives/screen_reader';
import { exportState } from '~/store/serialization';
import { EXPORT_OPTION_CANVAS, EXPORT_OPTIONS } from './options';
import s from './status_selected.module.scss';

/** Every selectable format — the per-card ones plus the canvas export. */
const ALL_OPTIONS = [...EXPORT_OPTIONS, EXPORT_OPTION_CANVAS] as const;

type ExportKey = (typeof ALL_OPTIONS)[number]['key'];

/** We default to first option in list. */
const DEFAULT_KEY = EXPORT_OPTIONS[0];

export const StatusSelected = () => {
  const [selectedKey, setSelectedKey] = useState<ExportKey>(DEFAULT_KEY.key);

  // Find the selected option from the list of export options - if not found
  // we just default to the default option
  const selectedOption =
    ALL_OPTIONS.find((option) => option.key === selectedKey) ?? DEFAULT_KEY;

  const exportSelectedCards = (format: ExportKey) => {
    switch (format) {
      case 'api-request-code':
      case 'csv':
      case 'ai-narrative':
      case 'ai-infographic':
      case 'svg':
      case 'png':
        // TODO: Implement missing export flow
        toast(
          'Unsupported export format',
          "Feature hasn't been implemented yet.",
        );
        break;

      case 'canvas':
        exportState();
        break;
    }
  };

  return (
    <section className={s.container}>
      <fieldset className={s['fieldset-container']} aria-label="Export format">
        <ScreenReaderOnly element="legend">
          Choose an export format
        </ScreenReaderOnly>

        <ul className={s['options-container']}>
          {EXPORT_OPTIONS.map((option) => (
            <li key={option.key}>
              <Radio
                name="export-format"
                value={option.key}
                checked={selectedKey === option.key}
                onChange={() => setSelectedKey(option.key)}
              >
                <span className={s['option-container']} data-has-max-width>
                  <span className={s['option-title']}>{option.title}</span>
                  <span className={s['option-description']}>
                    {option.description}
                  </span>
                </span>
              </Radio>
            </li>
          ))}
        </ul>

        <div className={s['canvas-container']}>
          <Radio
            name="export-format"
            value={EXPORT_OPTION_CANVAS.key}
            checked={selectedKey === EXPORT_OPTION_CANVAS.key}
            onChange={() => setSelectedKey(EXPORT_OPTION_CANVAS.key)}
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
        </div>
      </fieldset>

      <Button
        className={s['button-download']}
        size="large"
        variant="border"
        tone="subtle-highlight"
        icon={selectedOption.icon}
        onClick={() => exportSelectedCards(selectedKey)}
      >
        {selectedOption.action}
      </Button>
    </section>
  );
};
