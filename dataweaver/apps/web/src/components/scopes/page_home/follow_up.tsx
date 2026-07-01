'use client';

import { EASE_LINEAR } from '@package/tokens/ts';
import { m } from 'motion/react';
import { Button } from '~/components/elements/button';
import type { FollowUp as FollowUpData } from '~/server/types';
import s from './follow_up.module.scss';

interface FollowUpProps {
  prompt: string;
  followUp: FollowUpData;
  onSelect: (followUp: string) => void;
}

export const FollowUp = ({ prompt, followUp, onSelect }: FollowUpProps) => {
  return (
    <m.section
      className={s['outer-container']}
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.1, ease: EASE_LINEAR }}
    >
      <div className={s['inner-container']}>
        <p className={s.question}>{prompt}</p>

        <div className={s.answer}>{followUp.summary}</div>
        <div className={s.answer}>{followUp.question}</div>

        {followUp?.options?.length > 0 && (
          <ul className={s['prompts-container']}>
            {followUp.options.map((option) => (
              <li key={option}>
                <Button
                  size="medium"
                  variant="flat"
                  tone="accent-subtle"
                  onClick={() => onSelect(option)}
                >
                  {option}
                </Button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </m.section>
  );
};
