import { EASE_LINEAR } from '@package/tokens/ts';
import { m } from 'motion/react';
import { Button } from '~/components/elements/button';
import { IconClose } from '~/components/primitives/icons/close';
import { IconInfo } from '~/components/primitives/icons/info';
import s from './intro.module.scss';

export const EXAMPLE_PROMPTS = [
  'Which countries have the highest access to mobile phones?',
  'Compare GDP and population growth globally over the last 50 years.',
  'What fraction of the world is forest?',
] as const;

interface IntroProps {
  onSelect: (example: string, index: number) => void;
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
      <div className={s['middle-container']}>
        <div className={s['inner-container']}>
          <Button
            className={s['button-close']}
            icon={IconClose}
            size="large"
            variant="flat"
            tone="subtle"
            aria-label="Close"
            onClick={onClose}
          />

          <div className={s['content-container']}>
            <h2 className={s.title}>Shape your data discovery</h2>

            <p className={s.description}>
              Data Commons pairs a fluid canvas with an AI data agent. Enter a
              question to surface data from across Data Commons, then weave your
              findings together—expanding, positioning, and connecting charts
              across an unbounded workspace.
            </p>

            <p className={s.question}>
              Ask a question to start, or try an example:
            </p>

            <ul className={s['examples-container']}>
              {EXAMPLE_PROMPTS.map((example, index) => (
                <li key={example}>
                  <Button
                    size="medium"
                    variant="flat"
                    tone="accent-subtle"
                    onClick={() => onSelect(example, index)}
                  >
                    {example}
                  </Button>
                </li>
              ))}
            </ul>
          </div>

          <p className={s['notice-container']}>
            <IconInfo className={s['icon-info']} aria-hidden="true" />
            This tool currently does not save your progress. Please export
            before closing tab to retain data.
          </p>
        </div>
      </div>
    </m.section>
  );
};
