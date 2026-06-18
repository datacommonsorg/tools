'use client';

import { EASE_LINEAR } from '@package/tokens/ts';
import { m } from 'motion/react';
import { Button } from '~/components/elements/button';
import { useQueryActions } from '~/components/scopes/atlas/query_provider';
import { useDataWeaverStore } from '~/store';
import s from './status.module.scss';

export const Status = () => {
  const { currentStatus, nodes, latestNodeId } = useDataWeaverStore();
  const { cancelQuery } = useQueryActions();
  const latestNode = latestNodeId ? nodes[latestNodeId] : null;
  const { query } = latestNode || {};

  return (
    <m.aside
      className={s.container}
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.1, ease: EASE_LINEAR }}
    >
      <h2 className={s['prompt-value']}>{query}</h2>

      <p className={s['indicator-message']}>{currentStatus}</p>

      <Button
        className={s['button-cancel']}
        size="small"
        variant="border"
        tone="subtle"
        onClick={cancelQuery}
      >
        Cancel
      </Button>
    </m.aside>
  );
};
