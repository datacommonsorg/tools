import { EASE_LINEAR } from '@package/tokens/ts';
import { m } from 'motion/react';
import { Button } from '~/components/elements/button';
import { IconClose } from '~/components/primitives/icons/close';
import { IconInfo } from '~/components/primitives/icons/info';
import s from './intro.module.scss';

const EXAMPLE_PROMPTS = [
  'How access to electricity has changed across countries in Africa?',
  'Which countries have the highest access to mobile phones?',
  'Compare GDP and population growth globally over the last 50 years.',
  'What fraction of the world is forest?',
] as const;

interface IntroProps {
  onSelect: (example: string) => void;
  onClose: () => void;
}

export const Intro = ({ onSelect, onClose }: IntroProps) => {
  return (
    <m.section
      className={s['outer-container']}
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.1, ease: EASE_LINEAR }}
    >
      <div className={s['inner-container']}>
        <Button
          className={s['button-close']}
          icon={IconClose}
          size="medium"
          variant="flat"
          tone="subtle"
          aria-label="Close"
          onClick={onClose}
        />

        <div className={s['content-container']}>
          <h2 className={s.title}>
            Let's discover what you can do with Data Commons
          </h2>

          <p className={s.description}>
            Explore data visually on an infinite canvas with your AI thought
            partner. Find, visualize, and understand rich data from Data Commons
            to deepen your research exploration.
          </p>

          <p className={s.question}>
            Ask Data Weaver your research question, or try examples like:
          </p>

          <ul className={s['examples-container']}>
            {EXAMPLE_PROMPTS.map((example) => (
              <li key={example}>
                <Button
                  size="medium"
                  variant="flat"
                  tone="accent-subtle"
                  onClick={() => onSelect(example)}
                >
                  {example}
                </Button>
              </li>
            ))}
          </ul>
        </div>

        <p className={s['notice-container']}>
          <IconInfo className={s['icon-info']} aria-hidden="true" />
          This tool currently does not save your progress. Please export before
          closing tab to retain data.
        </p>
      </div>
    </m.section>
  );
};
