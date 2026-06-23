'use client';

import { EASE_LINEAR } from '@package/tokens/ts';
import { m } from 'motion/react';
import { Button } from '~/components/elements/button';
import s from './follow_up.module.scss';

export interface QuestionAndAnswers {
  /** The question the user asked, echoed back as a chat bubble. */
  question: string;

  /** The assistant's answer. Newlines are preserved. */
  answer: string;

  /** Suggested follow-up prompts, rendered as selectable pills. */
  prompts: string[];
}

interface FollowUpProps {
  followUp: QuestionAndAnswers;
  onSelect: (followUp: string) => void;
}

export const FollowUp = ({ followUp, onSelect }: FollowUpProps) => {
  return (
    <m.section
      className={s['outer-container']}
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.1, ease: EASE_LINEAR }}
    >
      <div className={s['inner-container']}>
        <p className={s.question}>{followUp.question}</p>

        <div className={s.answer}>{followUp.answer}</div>

        {followUp.prompts.length > 0 && (
          <ul className={s['prompts-container']}>
            {followUp.prompts.map((prompt) => (
              <li key={prompt}>
                <Button
                  size="medium"
                  variant="flat"
                  tone="accent-subtle"
                  onClick={() => onSelect(prompt)}
                >
                  {prompt}
                </Button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </m.section>
  );
};
