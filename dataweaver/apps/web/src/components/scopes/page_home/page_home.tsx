'use client';

import { AnimatePresence } from 'motion/react';
import { useEffect, useState } from 'react';
import { useQueryActions } from '~/components/scopes/atlas/query_provider';
import { type Disambiguation, STATUS } from '~/server/types';
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
  const [followUp, setFollowUp] = useState<Disambiguation | null>(null);
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
    const disambiguations = latestNode?.results
      ? Object.values(latestNode.results)
          .map((r) => r.disambiguation)
          .filter(Boolean)
      : [];
    // TODO - we currently can get more than one disambiguation, as the api will return
    // one per place in the query. Here I'm just using the first one, but we'll need to figure
    // out a better way to handle this
    const disambiguation = disambiguations[0];
    if (latestNode && disambiguation && currentStatus === STATUS.complete) {
      setFollowUp(disambiguation);
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
