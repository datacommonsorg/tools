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
 * @fileoverview Renders the disclaimer and policy links under the prompt box.
 */

import { Link } from '@/src/components/link';

/**
 * The AI-content wording under the prompt box. Each answer has its own wording
 * (DISCLAIMER_TEXT in note_disclaimer.tsx).
 */
export const COMPOSER_DISCLAIMER_TEXT =
  'This site is protected by reCAPTCHA. Data overviews are synthesized by Gemini. Gemini is AI and can make mistakes; please verify content against primary source data.';

/** Google policies linked from the composer note. */
export const POLICY_LINKS = {
  privacy: {
    label: 'Privacy Policy',
    href: 'https://policies.google.com/privacy',
  },
  terms: {
    label: 'Terms of Service',
    href: 'https://policies.google.com/terms',
  },
} as const;

/** Link styling; always underlined so links do not rely on color alone. */
const POLICY_LINK_CLASS = 'text-theme-primary underline hover:no-underline';

/** Disclaimer and Google policy links shown under the follow-up prompt box. */
export function ComposerNote() {
  return (
    <div className="text-center text-caption text-muted max-w-prompt px-2">
      <span>{COMPOSER_DISCLAIMER_TEXT}</span> Google{' '}
      <Link href={POLICY_LINKS.privacy.href} className={POLICY_LINK_CLASS}>
        {POLICY_LINKS.privacy.label}
      </Link>{' '}
      and{' '}
      <Link href={POLICY_LINKS.terms.href} className={POLICY_LINK_CLASS}>
        {POLICY_LINKS.terms.label}
      </Link>
      .
    </div>
  );
}
