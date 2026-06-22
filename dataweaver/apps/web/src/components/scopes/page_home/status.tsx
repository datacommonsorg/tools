'use client';

import { EASE_LINEAR } from '@package/tokens/ts';
import { m } from 'motion/react';
import { Button } from '~/components/elements/button';
import { useQueryActions } from '~/components/scopes/atlas/query_provider';
import s from './status.module.scss';

interface StatusProps {
  prompt: string;
  status: string;
}

export const Status = ({ prompt, status }: StatusProps) => {
  const { queryCancel } = useQueryActions();

  return (
    <m.aside
      className={s.container}
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.1, ease: EASE_LINEAR }}
    >
      <h2 className={s['prompt-value']}>{prompt}</h2>

      <p className={s['indicator-message']}>{status}</p>

      <Button
        className={s['button-cancel']}
        size="small"
        variant="border"
        tone="subtle"
        onClick={queryCancel}
      >
        Cancel
      </Button>
    </m.aside>
  );
};
