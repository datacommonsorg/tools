'use client';

import { AnimatePresence } from 'motion/react';
import { useEffect, useState } from 'react';
import { useQueryActions } from '~/components/scopes/atlas/query_provider';
import { Intro } from './intro';
import s from './page_home.module.scss';
import { Prompt } from './prompt';
import { Status } from './status';

export const PageHome = () => {
  const { status, runPrompt } = useQueryActions();

  const [isIntroVisible, setIsIntroVisible] = useState(true);
  const [promptValue, setPromptValue] = useState('');

  // Auto close intro if we have a status and it's visible
  useEffect(() => {
    if (status && isIntroVisible) setIsIntroVisible(false);
  }, [status, isIntroVisible]);

  const submit = (promptValue: string) => {
    runPrompt(promptValue);
    setPromptValue('');
    setIsIntroVisible(false);
  };

  return (
    <div className={s.container}>
      <AnimatePresence initial={false} mode="wait">
        {isIntroVisible && !status && (
          <Intro
            key="intro"
            onSelect={submit}
            onClose={() => setIsIntroVisible(false)}
          />
        )}

        {status && !isIntroVisible && <Status key="status" status={status} />}
      </AnimatePresence>

      <Prompt
        value={promptValue}
        onValueChange={setPromptValue}
        onSubmit={submit}
      />
    </div>
  );
};
