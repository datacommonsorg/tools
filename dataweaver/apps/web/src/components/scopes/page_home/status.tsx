'use client';

import { EASE_LINEAR } from '@package/tokens/ts';
import { m } from 'motion/react';
import { useRef } from 'react';
import { Button } from '~/components/elements/button';
import { IconStatusIndicator } from '~/components/primitives/icons/status_indicator';
import { useQueryActions } from '~/components/scopes/atlas/query_provider';
import { useAutoFocus } from '~/hooks/use_auto_focus';
import s from './status.module.scss';

interface StatusProps {
  prompt: string;
  status: string;
}

export const Status = ({ prompt, status }: StatusProps) => {
  const { queryCancel } = useQueryActions();
  const cancelButtonRef = useRef<HTMLButtonElement>(null);

  useAutoFocus(cancelButtonRef);

  return (
    <m.aside
      className={s.container}
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.1, ease: EASE_LINEAR }}
    >
      <h2 className={s['prompt-value']}>{prompt}</h2>

      <div className={s['indicator-message']} role="status">
        <IconStatusIndicator aria-hidden="true" />
        <p>{status}</p>
      </div>

      <Button
        ref={cancelButtonRef}
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
