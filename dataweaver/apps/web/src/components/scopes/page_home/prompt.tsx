'use client';

import { EASE_LINEAR, EASE_OUT } from '@package/tokens/ts';
import { AnimatePresence, m } from 'motion/react';
import { useId } from 'react';
import { Button } from '~/components/elements/button';
import { Tag } from '~/components/elements/tag';
import { IconArrowUp } from '~/components/primitives/icons/arrow_up';
import { ScreenReaderOnly } from '~/components/primitives/screen_reader';
import type { QueryTag } from '~/components/scopes/atlas/query_provider';
import s from './prompt.module.scss';

/** Placeholder text for the prompt input. */
const PROMPT_PLACEHOLDER = 'What data would you like to explore?';

interface PromptProps {
  value: string;
  tags: QueryTag[];
  onValueChange: (value: string) => void;
  onSubmit: (value: string) => void;
  onRemoveTag: (id: string) => void;
}

export const Prompt = ({
  value,
  tags,
  onValueChange,
  onSubmit,
  onRemoveTag,
}: PromptProps) => {
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
      <AnimatePresence initial={false}>
        {tags.length > 0 && (
          <m.div
            // Here we animate parent as inner container here has padding. If we
            // animate element with padding then height trick here doesn't work
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{
              height: { duration: 0.5, ease: EASE_OUT },
              opacity: { duration: 0.1, ease: EASE_LINEAR },
            }}
          >
            <ul className={s['tags-inner-container']}>
              <AnimatePresence initial={false}>
                {tags.map((tag) => (
                  <m.li
                    key={tag.id}
                    layout="position"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    transition={{
                      opacity: { duration: 0.1, ease: EASE_LINEAR },
                      layout: { duration: 0.5, ease: EASE_OUT },
                    }}
                  >
                    <Tag
                      label={tag.label}
                      onRemove={() => onRemoveTag(tag.id)}
                    />
                  </m.li>
                ))}
              </AnimatePresence>
            </ul>
          </m.div>
        )}
      </AnimatePresence>

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

      <Button
        className={s['button-submit']}
        type="submit"
        size="large"
        variant="border"
        tone="prominent"
        icon={IconArrowUp}
        aria-label="Submit prompt"
        isDisabled={!hasValue}
      />
    </form>
  );
};
