/**
 * @fileoverview Hook that resizes a single-row textarea to fit its content and
 * reports whether the text spans more than one line.
 */

import { RefObject, useLayoutEffect, useState } from "react";

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
 * @param textareaRef The textarea to size.
 * @param value The textarea's current controlled value.
 * @returns Whether `value` is non-empty and spans more than one line.
 */
export function useTextareaAutosize(
  textareaRef: RefObject<HTMLTextAreaElement | null>,
  value: string,
): boolean {
  const [isExpanded, setIsExpanded] = useState(false);

  useLayoutEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    const prev = el.style.height;
    el.style.height = "auto";
    const hasContent = value.length > 0;
    setIsExpanded(hasContent && el.scrollHeight > el.clientHeight);
    const next = `${hasContent ? el.scrollHeight : el.clientHeight}px`;
    el.style.height = prev;
    void el.offsetHeight;
    el.style.height = next;
  }, [value, textareaRef]);

  return isExpanded;
}
