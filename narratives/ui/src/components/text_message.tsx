/**
 * Copyright 2026 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
 * implied. See the License for the specific language governing
 * permissions and limitations under the License.
 */

/**
 * @fileoverview Renders an operator-configured message whose only Markdown is
 * links, such as the chat-unavailable message.
 */

import ReactMarkdown, { type Components } from 'react-markdown';
import { Link } from '@/src/components/link';

/**
 * Markdown overrides for the message. Module-level so their identity is
 * stable. Links open in the same tab: the message is shown where chat cannot
 * be used, so there is nothing on the page to keep.
 */
const MESSAGE_COMPONENTS: Components = {
  a: ({ children, href }) => (
    <Link
      href={href ?? ''}
      target="_self"
      className="text-theme-primary underline hover:no-underline"
    >
      {children}
    </Link>
  ),
};

/** Elements kept from the parsed message; everything else renders as text. */
const ALLOWED_ELEMENTS = ['a'];

interface MessageTextProps {
  /** Message text; `[label](url)` renders as a link. */
  message: string;
}

/**
 * Inline message text with its Markdown links rendered through `Link`, so an
 * unsafe URL renders as plain text. Other Markdown, paragraph breaks
 * included, renders as its text content, so the result flows inline in the
 * caller's own paragraph.
 */
export function MessageText({ message }: MessageTextProps) {
  return (
    <ReactMarkdown
      allowedElements={ALLOWED_ELEMENTS}
      unwrapDisallowed
      components={MESSAGE_COMPONENTS}
    >
      {message}
    </ReactMarkdown>
  );
}
