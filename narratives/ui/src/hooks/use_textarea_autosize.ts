/**
 * @fileoverview Hook that resizes a single-row textarea to fit its content and
 * reports whether the text spans more than one line and whether it scrolls.
 */

import { type RefObject, useLayoutEffect, useState } from 'react';

/**
 * Sizes a `rows={1}` `<textarea>` to its content whenever `value` changes, and
 * returns whether the content runs past one line — wrapped or an explicit
 * newline.
 *
 * At height auto a `rows={1}` textarea reports one line as its clientHeight.
 * An empty box stays one line: a wrapping placeholder also overflows. The old
 * height is restored and flushed before the new one is set, so a CSS `height`
 * transition on the element animates between them.
 *
 * The height stops at the element's CSS `max-height`, so the transition runs
 * between heights the box actually shows, and `overflow-y` is set inline:
 * hidden while the text fits (no scrollbar flashing as a line is added), auto
 * once it passes the cap.
 *
 * `isScrolling` latches: it turns on when the text passes the cap and stays on
 * until the text is back to one line. A caller that widens the textarea while
 * it scrolls rewraps the text onto fewer lines, which would otherwise drop it
 * back under the cap and flip the layout on every keystroke at the boundary.
 *
 * @param textareaRef The textarea to size.
 * @param value The textarea's current controlled value.
 * @returns `isExpanded`: whether `value` is non-empty and spans more than one
 *   line. `isScrolling`: whether it has passed the max height since it last
 *   fit on one line.
 */
export const useTextareaAutosize = (
  textareaRef: RefObject<HTMLTextAreaElement | null>,
  value: string,
): { isExpanded: boolean; isScrolling: boolean } => {
  const [isExpanded, setIsExpanded] = useState(false);
  const [isScrolling, setIsScrolling] = useState(false);

  useLayoutEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    const prev = el.style.height;
    el.style.height = 'auto';
    el.style.overflowY = 'hidden';
    const hasContent = value.length > 0;
    const isMultiline = hasContent && el.scrollHeight > el.clientHeight;
    setIsExpanded(isMultiline);
    const maxHeight = Number.parseFloat(getComputedStyle(el).maxHeight);
    const contentHeight = hasContent ? el.scrollHeight : el.clientHeight;
    const isOverLimit = Number.isFinite(maxHeight) && contentHeight > maxHeight;
    setIsScrolling(
      (wasScrolling) => isMultiline && (wasScrolling || isOverLimit),
    );
    el.style.height = prev;
    void el.offsetHeight;
    el.style.height = `${isOverLimit ? maxHeight : contentHeight}px`;
    el.style.overflowY = isOverLimit ? 'auto' : 'hidden';
  }, [value, textareaRef]);

  return { isExpanded, isScrolling };
};
