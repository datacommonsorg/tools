'use client';

import { useId } from 'react';
import { Button } from '~/components/elements/button';
import { IconArrowUp } from '~/components/primitives/icons/arrow_up';
import { ScreenReaderOnly } from '~/components/primitives/screen_reader';
import s from './prompt.module.scss';

/** Placeholder text for the prompt input. */
const PROMPT_PLACEHOLDER = 'What data would you like to explore?';

interface PromptProps {
  value: string;
  onValueChange: (value: string) => void;
  onSubmit: (value: string) => void;
}

export const Prompt = ({ value, onValueChange, onSubmit }: PromptProps) => {
  const inputId = useId();

  const trimmedValue = value.trim();
  const hasValue = Boolean(trimmedValue);

  const submitted = () => {
    if (hasValue) onSubmit(trimmedValue);
  };

  return (
    <form
      className={s.container}
      onSubmit={(event) => {
        event.preventDefault();
        submitted();
      }}
    >
      <ScreenReaderOnly element="label" htmlFor={inputId}>
        {PROMPT_PLACEHOLDER}
      </ScreenReaderOnly>

      <textarea
        id={inputId}
        className={s.input}
        value={value}
        rows={1}
        placeholder={PROMPT_PLACEHOLDER}
        onChange={(event) => onValueChange(event.target.value)}
        onKeyDown={(event) => {
          // Submit if enter is pressed without shift or during IME composition
          if (
            event.key === 'Enter' &&
            !event.shiftKey &&
            !event.nativeEvent.isComposing
          ) {
            event.preventDefault();
            submitted();
          }
        }}
      />

      {/* TODO: In designs this is a button with an outline. Review + explore real disabled styles. */}
      <Button
        className={s['button-submit']}
        type="submit"
        icon={IconArrowUp}
        size="large"
        aria-label="Submit prompt"
        isDisabled={!hasValue}
      />
    </form>
  );
};
