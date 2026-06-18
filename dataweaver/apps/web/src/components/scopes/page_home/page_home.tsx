'use client';

import { AnimatePresence } from 'motion/react';
import { useState } from 'react';
import { useQueryActions } from '~/components/scopes/atlas/query_provider';
import { FollowUp, type QuestionAndAnswers } from './follow_up';
import { Intro } from './intro';
import s from './page_home.module.scss';
import { Prompt } from './prompt';
import { Status } from './status';

export const PageHome = () => {
  const { runPrompt } = useQueryActions();

  const [isIntroVisible, setIsIntroVisible] = useState(true);
  const [followUp, setFollowUp] = useState<QuestionAndAnswers | null>(null);
  const [promptValue, setPromptValue] = useState('');

  const status = null;

  const submit = (value = promptValue) => {
    runPrompt(value);
    setPromptValue('');
    setIsIntroVisible(false);
    setFollowUp(null);
  };

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

        {followUp && !status && (
          <FollowUp key="follow-up" followUp={followUp} onSelect={submit} />
        )}
      </AnimatePresence>
      <Status />
      <Prompt
        value={promptValue}
        onValueChange={setPromptValue}
        onSubmit={submit}
      />
    </div>
  );
};
