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
 * @fileoverview Type declarations for the Google Cloud reCAPTCHA Enterprise
 * browser SDK (`https://www.google.com/recaptcha/enterprise.js`).
 */

/** Color theme supported by the reCAPTCHA Enterprise checkbox widget. */
export type GrecaptchaTheme = 'light' | 'dark';

/** Widget size supported by the reCAPTCHA Enterprise checkbox widget. */
export type GrecaptchaSize = 'normal' | 'compact';

/** Options accepted by `grecaptcha.enterprise.render`. */
export interface GrecaptchaRenderParameters {
  sitekey: string;
  theme?: GrecaptchaTheme;
  size?: GrecaptchaSize;
  callback?: (token: string) => void;
  'expired-callback'?: () => void;
  'error-callback'?: () => void;
}

/** Subset of the `window.grecaptcha.enterprise` client API used by the UI. */
export interface GrecaptchaEnterprise {
  ready(callback: () => void): void;
  render(
    container: HTMLElement,
    parameters: GrecaptchaRenderParameters,
  ): number;
  reset(widgetId?: number): void;
}

/** Shape of the global `window.grecaptcha` object exposed by `enterprise.js`. */
export interface GrecaptchaGlobal {
  enterprise?: GrecaptchaEnterprise;
}

declare global {
  interface Window {
    grecaptcha?: GrecaptchaGlobal;
  }
}
