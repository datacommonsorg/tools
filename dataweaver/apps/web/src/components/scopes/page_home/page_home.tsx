'use client';

import { AnimatePresence } from 'motion/react';
import { useEffect, useState } from 'react';
import { useQueryActions } from '~/components/scopes/atlas/query_provider';
import { STATUS } from '~/server/types';
import { useAtlasStore } from '~/store/store';
import { FollowUp, type QuestionAndAnswers } from './follow_up';
import { Intro } from './intro';
import s from './page_home.module.scss';
import { Prompt } from './prompt';
import { Status } from './status';

export const PageHome = () => {
  const { runPrompt } = useQueryActions();
  const { currentStatus, nodes, latestNodeId } = useAtlasStore();
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

  useEffect(() => {
    if (Object.values(nodes).length > 0) setIsIntroVisible(false);
  }, [nodes]);

  const showStatus =
    !isIntroVisible &&
    currentStatus !== STATUS.complete &&
    currentStatus !== STATUS.idle;

  useEffect(() => {
    const node = latestNodeId ? nodes[latestNodeId] : null;
    const disambiguations = node?.results
      ? Object.values(node.results)
          .map((r) => r.disambiguation)
          .filter(Boolean)
      : [];
    const disambiguation = disambiguations[0];
    if (node && disambiguation && currentStatus === STATUS.complete) {
      setFollowUp({
        question: node.query,
        answer: disambiguation.summary,
        followUp: disambiguation.question,
        prompts: disambiguation.options,
      });
    } else {
      setFollowUp(null);
    }
  }, [currentStatus, latestNodeId, nodes]);

  return (
    <div className={s.container}>
      <AnimatePresence initial={false} mode="wait">
        {isIntroVisible && (
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
