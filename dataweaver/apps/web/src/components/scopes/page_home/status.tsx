'use client';

import { EASE_LINEAR } from '@package/tokens/ts';
import { m } from 'motion/react';
import { Button } from '~/components/elements/button';
import {
  type Status as StatusType,
  useQueryActions,
} from '~/components/scopes/atlas/query_provider';
import s from './status.module.scss';

interface StatusProps {
  status: StatusType;
}

export const Status = ({ status }: StatusProps) => {
  const { cancelRunningPrompt } = useQueryActions();

  return (
    <m.aside
      className={s.container}
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.1, ease: EASE_LINEAR }}
    >
      <h2 className={s['prompt-value']}>{status.promptValue}</h2>

      <p className={s['indicator-message']}>{status.indicatorMessage}</p>

      <Button
        className={s['button-cancel']}
        size="small"
        variant="border"
        tone="subtle"
        onClick={cancelRunningPrompt}
      >
        Cancel
      </Button>
    </m.aside>
  );
};
