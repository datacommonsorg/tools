'use client';

import { AnimatePresence } from 'motion/react';
import { useState } from 'react';
import { useQueryActions } from '~/components/scopes/atlas/query_provider';
import { Intro } from './intro';
import s from './page_home.module.scss';
import { Prompt } from './prompt';

export const PageHome = () => {
  const { runPrompt } = useQueryActions();

  const [isIntroVisible, setIsIntroVisible] = useState(true);
  const [promptValue, setPromptValue] = useState('');

  const submit = () => {
    runPrompt(promptValue);
    setPromptValue('');
    setIsIntroVisible(false);
  };

  return (
    <div className={s.container}>
      <AnimatePresence initial={false}>
        {isIntroVisible && (
          <Intro onSelect={submit} onClose={() => setIsIntroVisible(false)} />
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
