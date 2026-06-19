'use client';

import { AnimatePresence } from 'motion/react';
import { useMemo, useState } from 'react';
import { useQueryActions } from '~/components/scopes/atlas/query_provider';
import { STATUS } from '~/server/types';
import { useDataWeaverStore } from '~/store/store';
import { FollowUp, type QuestionAndAnswers } from './follow_up';
import { Intro } from './intro';
import s from './page_home.module.scss';
import { Prompt } from './prompt';
import { Status } from './status';

export const PageHome = () => {
  const { runPrompt } = useQueryActions();
  const { currentStatus, nodes, latestNodeId } = useDataWeaverStore();
  const latestNode = latestNodeId ? nodes[latestNodeId] : null;
  const query = latestNode?.query ?? '';

  const [isIntroVisible, setIsIntroVisible] = useState(true);
  const [followUp, setFollowUp] = useState<QuestionAndAnswers | null>(null);
  const [promptValue, setPromptValue] = useState('');

  const submit = (value = promptValue) => {
    runPrompt(value);
    setPromptValue('');
    setIsIntroVisible(false);
    setFollowUp(null);
  };

  const showIntro = useMemo(() => {
    return isIntroVisible && currentStatus !== STATUS.complete;
  }, [isIntroVisible, currentStatus]);

  const showStatus = useMemo(() => {
    return !isIntroVisible && currentStatus !== STATUS.complete;
  }, [isIntroVisible, currentStatus]);

  return (
    <div className={s.container}>
      <AnimatePresence initial={false} mode="wait">
        {showIntro && (
          <Intro
            key="intro"
            onSelect={(selected) => {
              submit(selected);
            }}
            onClose={() => setIsIntroVisible(false)}
          />
        )}

        {followUp && !showStatus && (
          <FollowUp key="follow-up" followUp={followUp} onSelect={submit} />
        )}
        {showStatus && (
          <Status key="status" prompt={query} status={currentStatus} />
        )}
      </AnimatePresence>
      <Prompt
        value={promptValue}
        onValueChange={setPromptValue}
        onSubmit={submit}
      />
    </div>
  );
};
