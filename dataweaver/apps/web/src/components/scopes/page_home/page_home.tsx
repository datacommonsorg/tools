'use client';

import { AnimatePresence } from 'motion/react';
import { useEffect, useState } from 'react';
import { useQueryActions } from '~/components/scopes/atlas/query_provider';
import { type FollowUp as FollowUpData, STATUS } from '~/server/types';
import { useAtlasStore } from '~/store/store';
import { FollowUp } from './follow_up';
import { Intro } from './intro';
import s from './page_home.module.scss';
import { Prompt } from './prompt';
import { Status } from './status';

export const PageHome = () => {
  const { runPrompt } = useQueryActions();
  const currentStatus = useAtlasStore((s) => s.currentStatus);
  const latestNode = useAtlasStore((s) =>
    s.latestNodeId ? s.nodes[s.latestNodeId] : null,
  );
  const hasNodes = useAtlasStore((s) => Object.keys(s.nodes).length > 0);
  const query = latestNode?.query ?? '';

  const [isIntroVisible, setIsIntroVisible] = useState(true);
  const [followUp, setFollowUp] = useState<FollowUpData | null>(null);
  const [promptValue, setPromptValue] = useState('');

  const submit = (value = promptValue) => {
    runPrompt(value);
    setPromptValue('');
    setIsIntroVisible(false);
    setFollowUp(null);
  };

  useEffect(() => {
    if (hasNodes) setIsIntroVisible(false);
  }, [hasNodes]);

  const showStatus =
    !isIntroVisible &&
    currentStatus !== STATUS.complete &&
    currentStatus !== STATUS.idle;

  useEffect(() => {
    const followUps = latestNode?.results
      ? Object.values(latestNode.results)
          .map((r) => r.followUp)
          .filter(Boolean)
      : [];
    // TODO - we currently can get more than one follow-up, as the api will return
    // one per place in the query. Here I'm just using the first one, but we'll need to figure
    // out a better way to handle this
    const firstFollowUp = followUps[0];
    if (latestNode && firstFollowUp && currentStatus === STATUS.complete) {
      setFollowUp(firstFollowUp);
    } else {
      setFollowUp(null);
    }
  }, [currentStatus, latestNode]);

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
          <FollowUp
            key="follow-up"
            prompt={query}
            followUp={followUp}
            onSelect={submit}
          />
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
