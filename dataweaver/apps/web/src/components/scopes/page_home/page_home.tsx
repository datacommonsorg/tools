'use client';

import { AnimatePresence } from 'motion/react';
import { useEffect, useMemo, useState } from 'react';
import { useQueryActions } from '~/components/scopes/atlas/query_provider';
import { useAtlasSelectedCards } from '~/components/scopes/atlas/use_atlas_selected_cards';

import { type FollowUp as FollowUpData, STATUS } from '~/server/types';
import { useAtlasStore } from '~/store/store';
import { FollowUp } from './follow_up';
import { Intro } from './intro';
import s from './page_home.module.scss';
import { Prompt, type PromptTag } from './prompt';
import { Status } from './status';

/** Show a tag per card up to this many; beyond it, collapse to a count tag. */
const MAX_VISIBLE_TAGS = 2;

interface PageHomeProps {
  examplePrompts: string[];
}

export const PageHome = ({ examplePrompts }: PageHomeProps) => {
  const { runPrompt } = useQueryActions();
  const currentStatus = useAtlasStore((s) => s.currentStatus);
  const latestNode = useAtlasStore((s) =>
    s.latestNodeId ? s.nodes[s.latestNodeId] : null,
  );
  const hasNodes = useAtlasStore((s) => Object.keys(s.nodes).length > 0);
  const query = latestNode ? latestNode.query : '';

  const selectedCards = useAtlasSelectedCards();
  const tags: PromptTag[] = useMemo(() => {
    if (selectedCards.length > MAX_VISIBLE_TAGS) {
      const selectedTitle = `${selectedCards.length} items selected on canvas`;
      return [{ id: 'total', title: selectedTitle }];
    }

    return selectedCards;
  }, [selectedCards]);

  const nodeDismissFollowUp = useAtlasStore((s) => s.nodeDismissFollowUp);

  const [isIntroVisible, setIsIntroVisible] = useState(true);
  const [followUp, setFollowUp] = useState<FollowUpData | null>(null);
  const [promptValue, setPromptValue] = useState('');

  const submitPrompt = (value = promptValue) => {
    runPrompt(value);
    setPromptValue('');
    setIsIntroVisible(false);
    setFollowUp(null);
  };

  useEffect(() => {
    if (hasNodes) setIsIntroVisible(false);
  }, [hasNodes]);

  const isStatusVisible =
    !isIntroVisible &&
    currentStatus !== STATUS.complete &&
    currentStatus !== STATUS.idle;

  useEffect(() => {
    const nodeFollowUp = latestNode?.followUp;
    if (latestNode && nodeFollowUp && currentStatus === STATUS.complete) {
      setFollowUp(nodeFollowUp);
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
            onSelect={submitPrompt}
            onClose={() => setIsIntroVisible(false)}
            prompts={examplePrompts}
          />
        )}

        {followUp && !isStatusVisible && (
          <FollowUp
            key="follow-up"
            prompt={query}
            followUp={followUp}
            onSelect={submitPrompt}
            onClose={() => {
              setFollowUp(null);
              if (latestNode) nodeDismissFollowUp(latestNode.id);
            }}
          />
        )}

        {isStatusVisible && (
          <Status key="status" prompt={query} status={currentStatus} />
        )}
      </AnimatePresence>

      <Prompt
        value={promptValue}
        tags={tags}
        onValueChange={setPromptValue}
        onSubmit={submitPrompt}
      />
    </div>
  );
};
