'use client';

import { AnimatePresence } from 'motion/react';
import { useState } from 'react';
import { useQueryActions } from '~/components/scopes/atlas/query_provider';
import { MOCK_FOLLOW_UP } from '~/configs/mock_follow_up';
import { FollowUp, type QuestionAndAnswers } from './follow_up';
import { EXAMPLE_PROMPTS, Intro } from './intro';
import s from './page_home.module.scss';
import { Prompt } from './prompt';
import { Status } from './status';

export const PageHome = () => {
  const { status, runPrompt } = useQueryActions();

  const [isIntroVisible, setIsIntroVisible] = useState(true);
  const [followUp, setFollowUp] = useState<QuestionAndAnswers | null>(null);
  const [promptValue, setPromptValue] = useState('');

  const submitPrompt = (promptValue: string) => {
    runPrompt(promptValue);
    setPromptValue('');
    setIsIntroVisible(false);
    setFollowUp(null);
  };

  const selectExample = (example: string, index: number) => {
    // TODO: For now this purely just previews when last intro prompt is
    // selected. This needs to be hooked up differently / reworked later but for
    // now allows us to demo UI
    if (index === EXAMPLE_PROMPTS.length - 1) {
      setIsIntroVisible(false);
      setFollowUp(MOCK_FOLLOW_UP);
      return;
    }

    submitPrompt(example);
  };

  return (
    <div className={s.container}>
      <AnimatePresence initial={false} mode="wait">
        {isIntroVisible && (
          <Intro
            key="intro"
            onSelect={selectExample}
            onClose={() => setIsIntroVisible(false)}
          />
        )}

        {followUp && (
          <FollowUp
            key="follow-up"
            followUp={followUp}
            onSelect={submitPrompt}
          />
        )}

        {status && <Status key="status" status={status} />}
      </AnimatePresence>

      <Prompt
        value={promptValue}
        onValueChange={setPromptValue}
        onSubmit={submitPrompt}
      />
    </div>
  );
};
