'use client';

import { EASE_LINEAR } from '@package/tokens/ts';
import { AnimatePresence, m } from 'motion/react';
import { type Ref, useId } from 'react';
import { Button } from '~/components/elements/button';
import { Tag } from '~/components/elements/tag';
import { IconArrowUp } from '~/components/primitives/icons/arrow_up';
import { ScreenReaderOnly } from '~/components/primitives/screen_reader';
import s from './prompt.module.scss';

/** Placeholder text for the prompt input. */
const PROMPT_PLACEHOLDER = 'What data would you like to explore?';

/** A read-only chip shown in the prompt, derived from the canvas selection. */
export interface PromptTag {
  id: string;
  title: string;
}

interface PromptProps {
  value: string;
  tags: PromptTag[];
  onValueChange: (value: string) => void;
  onSubmit: (value: string) => void;
  inputRef?: Ref<HTMLTextAreaElement>;
  isStatusVisible?: boolean;
}

export const Prompt = ({
  value,
  tags,
  onValueChange,
  onSubmit,
  inputRef,
  isStatusVisible = false,
}: PromptProps) => {
  const inputId = useId();

  const trimmedValue = value.trim();
  const hasValue = Boolean(trimmedValue);

  // isStatusVisible means a query is already in flight (Status panel showing);
  // block a second submit until it resolves.
  const submitted = () => {
    if (hasValue && !isStatusVisible) onSubmit(trimmedValue);
  };

  return (
    <form
      className={s.container}
      onSubmit={(event) => {
        event.preventDefault();
        submitted();
      }}
    >
      <div
        className={s['content-container']}
        data-is-status-visible={isStatusVisible}
      >
        <ScreenReaderOnly element="label" htmlFor={inputId}>
          {PROMPT_PLACEHOLDER}
        </ScreenReaderOnly>

        <textarea
          ref={inputRef}
          id={inputId}
          className={s.input}
          value={value}
          rows={1}
          placeholder={PROMPT_PLACEHOLDER}
          disabled={isStatusVisible}
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

        <div className={s['button-row-container']}>
          <ul className={s['tags-container']}>
            <AnimatePresence initial={false} mode="wait">
              <m.ul
                key={tags[0] ? tags[0].id : 'empty'}
                className={s['tags-container']}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.2, ease: EASE_LINEAR }}
              >
                <AnimatePresence>
                  {tags.map((tag) => (
                    <m.li
                      key={tag.id}
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      exit={{ opacity: 0 }}
                      transition={{ duration: 0.2, ease: EASE_LINEAR }}
                    >
                      <Tag label={tag.title} />
                    </m.li>
                  ))}
                </AnimatePresence>
              </m.ul>
            </AnimatePresence>
          </ul>

          <Button
            className={s['button-submit']}
            type="submit"
            size="extra-large"
            variant={hasValue ? 'flat' : 'border'}
            tone={hasValue ? 'accent' : 'subtle'}
            icon={IconArrowUp}
            aria-label="Submit prompt"
            isDisabled={!hasValue || isStatusVisible}
          />
        </div>
      </div>
    </form>
  );
};
