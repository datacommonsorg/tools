'use client';

import { AnimatePresence } from 'motion/react';
import { useEffect, useMemo, useState } from 'react';
import { useAtlasSelectedCards } from '~/components/scopes/atlas/hooks/use_atlas_selected_cards';
import { useQueryActions } from '~/components/scopes/atlas/query_provider';
import { STATUS } from '~/server/types';
import { useAtlasStore } from '~/store/store';
import { FollowUp, type QuestionAndAnswers } from './follow_up';
import { Intro } from './intro';
import s from './page_home.module.scss';
import { Prompt, type PromptTag } from './prompt';
import { Status } from './status';

/** Show a tag per card up to this many; beyond it, collapse to a count tag. */
const MAX_VISIBLE_TAGS = 2;

export const PageHome = () => {
  const { runPrompt } = useQueryActions();

  const { currentStatus, nodes, latestNodeId } = useAtlasStore();
  const latestNode = latestNodeId ? nodes[latestNodeId] : null;
  const query = latestNode ? latestNode.query : '';

  const selectedCards = useAtlasSelectedCards();
  const tags: PromptTag[] = useMemo(() => {
    if (selectedCards.length > MAX_VISIBLE_TAGS) {
      const selectedTitle = `${selectedCards.length} items selected on canvas`;
      return [{ id: 'total', title: selectedTitle }];
    }

    return selectedCards;
  }, [selectedCards]);

  const [isIntroVisible, setIsIntroVisible] = useState(true);
  const [followUp, setFollowUp] = useState<QuestionAndAnswers | null>(null);
  const [promptValue, setPromptValue] = useState('');

  const submitPrompt = (value = promptValue) => {
    runPrompt(value);
    setPromptValue('');
    setIsIntroVisible(false);
    setFollowUp(null);
  };

  useEffect(() => {
    if (Object.values(nodes).length > 0) setIsIntroVisible(false);
  }, [nodes]);

  const isStatusVisible =
    !isIntroVisible &&
    currentStatus !== STATUS.complete &&
    currentStatus !== STATUS.idle;

  return (
    <div className={s.container}>
      <AnimatePresence initial={false} mode="wait">
        {isIntroVisible && (
          <Intro
            key="intro"
            onSelect={submitPrompt}
            onClose={() => setIsIntroVisible(false)}
          />
        )}

        {followUp && !isStatusVisible && (
          <FollowUp
            key="follow-up"
            followUp={followUp}
            onSelect={submitPrompt}
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
