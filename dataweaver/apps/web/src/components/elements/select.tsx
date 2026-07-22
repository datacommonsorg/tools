'use client';

import { type ReactNode, useCallback, useRef, useState } from 'react';
import { mergeClassNames } from '~/functions/merge_class_names';
import { useClickOutside } from '~/hooks/use_click_outside';
import { useKeydown } from '~/hooks/use_keydown';
import s from './select.module.scss';

interface SelectProps<T> {
  options: T[];
  value: T;
  onSelect: (item: T) => void;
  getKey: (item: T) => string;
  renderOption: (item: T) => ReactNode;
  renderTrigger?: (item: T) => ReactNode;

  /** Optional floating prefix label (e.g. "Facet", "Sort by"). */
  label?: string;

  /** @default false */
  isDisabled?: boolean;

  'aria-label'?: string;
  className?: string;
}

export const Select = <T,>({
  options,
  value,
  onSelect,
  getKey,
  renderOption,
  renderTrigger,
  label,
  isDisabled = false,
  className,
  ...rest
}: SelectProps<T>) => {
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const optionRefs = useRef<(HTMLButtonElement | null)[]>([]);

  const close = useCallback(() => {
    setIsOpen(false);
  }, []);

  useClickOutside(containerRef, close, { isEnabled: isOpen });
  useKeydown('Escape', close, { isEnabled: isOpen });

  useKeydown(
    ['ArrowDown', 'ArrowUp'],
    (event) => {
      event.preventDefault();
      const focusedIndex = optionRefs.current.indexOf(
        document.activeElement as HTMLButtonElement | null,
      );
      const direction = event.code === 'ArrowDown' ? 1 : -1;
      const nextIndex =
        (focusedIndex + direction + options.length) % options.length;
      optionRefs.current[nextIndex]?.focus();
    },
    { isEnabled: isOpen },
  );

  const triggerContent = renderTrigger
    ? renderTrigger(value)
    : renderOption(value);

  return (
    <div
      ref={containerRef}
      className={mergeClassNames(s.container, className)}
      data-is-disabled={isDisabled}
    >
      {label && <span className={s.label}>{label}</span>}

      <button
        type="button"
        className={s.trigger}
        aria-haspopup="listbox"
        aria-expanded={isOpen}
        aria-label={rest['aria-label']}
        disabled={isDisabled}
        onPointerDown={(event) => event.stopPropagation()}
        onClick={() => setIsOpen(!isOpen)}
      >
        <span className={s['trigger-content']}>{triggerContent}</span>
        <span className={s.arrow} aria-hidden="true">
          ▾
        </span>
      </button>

      {isOpen && (
        <div
          className={s.dropdown}
          role="listbox"
          aria-label={rest['aria-label']}
        >
          {options.map((option, index) => {
            const key = getKey(option);
            const isSelected = getKey(value) === key;
            return (
              <button
                key={key}
                ref={(element) => {
                  optionRefs.current[index] = element;
                }}
                type="button"
                className={s.option}
                role="option"
                aria-selected={isSelected}
                data-is-selected={isSelected}
                onPointerDown={(event) => event.stopPropagation()}
                onClick={() => {
                  onSelect(option);
                  setIsOpen(false);
                }}
              >
                {renderOption(option)}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
};
