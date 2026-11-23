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
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

/**
 * @fileoverview Renders the fallback reCAPTCHA Enterprise checkbox dialog when
 * a chat POST receives HTTP 403 and pauses awaiting user verification.
 */

import { useCallback, useEffect, useId, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import {
  RECAPTCHA_MODAL_DESCRIPTION,
  RECAPTCHA_MODAL_EXPIRED_NOTE,
  RECAPTCHA_MODAL_LOAD_ERROR,
  RECAPTCHA_MODAL_LOADING_LABEL,
  RECAPTCHA_MODAL_TITLE,
  RECAPTCHA_MODAL_WIDGET_ERROR,
  RETRY_LABEL,
} from '@/src/config/copy_chat';
import { useChatSession } from '@/src/hooks/chat_session_context';
import type {
  GrecaptchaEnterprise,
  GrecaptchaSize,
} from '@/src/types/grecaptcha';
import { ensureRecaptchaScript } from '@/src/utils/load_recaptcha';

/** Standard width in pixels of the `normal` reCAPTCHA checkbox widget. */
const NORMAL_WIDGET_WIDTH_PX = 304;

/** Selector matching tabbable elements inside the dialog, including the checkbox iframe. */
const FOCUSABLE_SELECTOR =
  'button:not([disabled]), a[href], iframe:not([tabindex="-1"]), [tabindex]:not([tabindex="-1"]):not([disabled])';

/** Internal loading and rendering states for the checkbox widget inside the dialog. */
type WidgetState =
  | { status: 'loading' }
  | { status: 'ready'; notice: string | null }
  | { status: 'error'; message: string };

/** Props for {@link RecaptchaModalDialog}. */
interface RecaptchaModalDialogProps {
  checkboxSiteKey: string;
  onComplete: (token: string) => void;
  onCancel: () => void;
}

/** Props for {@link RecaptchaCheckboxWidget}. */
interface RecaptchaCheckboxWidgetProps {
  checkboxSiteKey: string;
  onComplete: (token: string) => void;
  onRetry: () => void;
}

/** Returns visible, tabbable descendants of `dialog` in DOM order. */
const getDialogFocusables = (dialog: HTMLElement): HTMLElement[] =>
  Array.from(dialog.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)).filter(
    (element) =>
      element.tabIndex >= 0 &&
      !element.closest('[hidden], [inert], [aria-hidden="true"]'),
  );

/**
 * Wraps `Tab` and `Shift+Tab` focus at the edges of `dialog`. Leaves focus
 * alone when an external `<iframe>` (Google's body-level challenge bubble)
 * currently holds focus.
 */
const trapDialogFocus = (
  event: KeyboardEvent,
  dialog: HTMLElement | null,
): void => {
  if (!dialog?.isConnected) return;
  const active = document.activeElement;
  if (active instanceof HTMLIFrameElement && !dialog.contains(active)) {
    return;
  }
  const focusables = getDialogFocusables(dialog);
  if (focusables.length === 0) {
    event.preventDefault();
    return;
  }
  const first = focusables[0];
  const last = focusables[focusables.length - 1];
  // The dialog itself holds focus on open; Tab enters its first control.
  if (active === dialog || !dialog.contains(active)) {
    event.preventDefault();
    first.focus();
    return;
  }
  if (event.shiftKey && active === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && active === last) {
    event.preventDefault();
    first.focus();
  }
};

/**
 * Picks `'compact'` when the widget host is narrower than the standard 304px
 * reCAPTCHA checkbox so the widget never overflows narrow viewports.
 */
const selectWidgetSize = (container: HTMLElement): GrecaptchaSize => {
  const availableWidth =
    container.parentElement?.clientWidth ?? container.clientWidth;
  return availableWidth > 0 && availableWidth < NORMAL_WIDGET_WIDTH_PX
    ? 'compact'
    : 'normal';
};

/**
 * Resets a rendered reCAPTCHA widget, ignoring errors if its iframe was
 * already torn down.
 */
const safeResetWidget = (
  enterprise: GrecaptchaEnterprise | null,
  widgetId: number | null,
): void => {
  if (enterprise === null || widgetId === null) return;
  try {
    enterprise.reset(widgetId);
  } catch {
    // Ignore reset failures if the iframe was already torn down.
  }
};

/**
 * Root-mounted modal gate that mounts {@link RecaptchaModalDialog} only while
 * verification is open, resetting all internal widget state between openings.
 */
export function RecaptchaModal() {
  const { verificationModal, completeVerification, cancelVerification } =
    useChatSession();

  if (verificationModal.status !== 'open' || typeof document === 'undefined') {
    return null;
  }

  // Portal to `document.body` so the modal sits outside the `inert` app shell
  // while keeping `document.body` interactive for Google's challenge bubble.
  return createPortal(
    <RecaptchaModalDialog
      checkboxSiteKey={verificationModal.checkboxSiteKey}
      onComplete={completeVerification}
      onCancel={cancelVerification}
    />,
    document.body,
  );
}

/** Open verification dialog hosting Google's reCAPTCHA Enterprise checkbox widget. */
function RecaptchaModalDialog({
  checkboxSiteKey,
  onComplete,
  onCancel,
}: Readonly<RecaptchaModalDialogProps>) {
  const dialogRef = useRef<HTMLDivElement | null>(null);
  const titleId = useId();
  const descriptionId = useId();
  const [renderAttempt, setRenderAttempt] = useState(0);

  const handleRetry = useCallback(() => {
    setRenderAttempt((attempt) => attempt + 1);
    // Keep focus inside the dialog as the Retry button unmounts.
    dialogRef.current?.focus();
  }, []);

  // Move initial focus into the dialog on mount. Capturing and restoring prior
  // focus lives in `useRecaptchaVerification` so it reads `activeElement`
  // before `AppLayout` becomes `inert` and restores it after `inert` clears.
  useEffect(() => {
    dialogRef.current?.focus();
  }, []);

  // Dismiss on Escape and trap Tab/Shift+Tab within the dialog.
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.defaultPrevented) return;
      if (event.key === 'Escape') {
        event.preventDefault();
        onCancel();
        return;
      }
      if (event.key === 'Tab') {
        trapDialogFocus(event, dialogRef.current);
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [onCancel]);

  return (
    <>
      {/* Pointer-only backdrop; Escape serves the keyboard. */}
      <div
        data-non-print="true"
        className="fixed inset-0 z-50 bg-scrim/30 motion-safe:animate-fade-in"
        onClick={onCancel}
        aria-hidden="true"
      />

      {/* Keep z-50 far below Google's floating challenge bubble (z-index ~2e9)
          and omit overflow clipping so the image-grid challenge is never cut off. */}
      <div
        data-non-print="true"
        className="fixed inset-0 z-50 flex items-center justify-center p-4 pointer-events-none"
      >
        <div
          ref={dialogRef}
          role="dialog"
          aria-modal="true"
          aria-labelledby={titleId}
          aria-describedby={descriptionId}
          tabIndex={-1}
          className="pointer-events-auto outline-none w-full max-w-xl rounded-dialog dialog-surface shadow-elevated py-8 px-10 flex flex-col gap-2 motion-safe:animate-enter items-start"
        >
          <h2
            id={titleId}
            className="text-headline-small-emphasized text-headline"
          >
            {RECAPTCHA_MODAL_TITLE}
          </h2>

          <p
            id={descriptionId}
            className="mb-2 text-body-large text-on-surface-variant"
          >
            {RECAPTCHA_MODAL_DESCRIPTION}
          </p>

          <RecaptchaCheckboxWidget
            key={renderAttempt}
            checkboxSiteKey={checkboxSiteKey}
            onComplete={onComplete}
            onRetry={handleRetry}
          />
        </div>
      </div>
    </>
  );
}

/**
 * Loads `enterprise.js` and renders one explicit checkbox widget instance.
 * Remounted via `key` on retry so each attempt starts with a fresh container.
 */
function RecaptchaCheckboxWidget({
  checkboxSiteKey,
  onComplete,
  onRetry,
}: Readonly<RecaptchaCheckboxWidgetProps>) {
  const widgetContainerRef = useRef<HTMLDivElement | null>(null);
  const [widgetState, setWidgetState] = useState<WidgetState>({
    status: 'loading',
  });

  useEffect(() => {
    const container = widgetContainerRef.current;
    if (!container?.isConnected) return;

    let isActive = true;
    let enterpriseClient: GrecaptchaEnterprise | null = null;
    let widgetId: number | null = null;

    // Retires callbacks, resets any active widget (dismissing open challenge
    // bubbles), and clears the host container for StrictMode-safe teardown.
    const teardownWidget = (): void => {
      isActive = false;
      const activeWidgetId = widgetId;
      widgetId = null;
      safeResetWidget(enterpriseClient, activeWidgetId);
      container.replaceChildren();
    };

    const handleWidgetError = (): void => {
      if (!isActive) return;
      teardownWidget();
      setWidgetState({
        status: 'error',
        message: RECAPTCHA_MODAL_WIDGET_ERROR,
      });
    };

    const handleTokenSolved = (token: string): void => {
      if (!isActive) return;
      if (token.trim() === '') {
        handleWidgetError();
        return;
      }
      isActive = false;
      onComplete(token);
    };

    const handleTokenExpired = (): void => {
      if (!isActive) return;
      safeResetWidget(enterpriseClient, widgetId);
      setWidgetState({
        status: 'ready',
        notice: RECAPTCHA_MODAL_EXPIRED_NOTE,
      });
    };

    const mountWidget = async (): Promise<void> => {
      let enterprise: GrecaptchaEnterprise;
      try {
        enterprise = await ensureRecaptchaScript();
      } catch (error) {
        if (!isActive) return;
        console.warn('[recaptcha] Failed to load enterprise.js:', error);
        teardownWidget();
        setWidgetState({
          status: 'error',
          message: RECAPTCHA_MODAL_LOAD_ERROR,
        });
        return;
      }

      if (!isActive || !container.isConnected) return;
      enterpriseClient = enterprise;
      // Clear any leftover nodes so StrictMode double-effects never hit
      // "reCAPTCHA has already been rendered in this element".
      container.replaceChildren();

      try {
        widgetId = enterprise.render(container, {
          sitekey: checkboxSiteKey,
          size: selectWidgetSize(container),
          callback: handleTokenSolved,
          'expired-callback': handleTokenExpired,
          'error-callback': handleWidgetError,
        });
        setWidgetState({ status: 'ready', notice: null });
      } catch (error) {
        if (!isActive) return;
        console.warn('[recaptcha] Failed to render checkbox widget:', error);
        teardownWidget();
        setWidgetState({
          status: 'error',
          message: RECAPTCHA_MODAL_LOAD_ERROR,
        });
      }
    };

    void mountWidget();
    return teardownWidget;
  }, [checkboxSiteKey, onComplete]);

  if (widgetState.status === 'error') {
    return (
      <div className="flex flex-col items-start gap-3">
        <p
          role="alert"
          className="w-full rounded-lg bg-error-surface px-3 py-2.5 text-body-medium text-error-strong"
        >
          {widgetState.message}
        </p>
        <button
          type="button"
          onClick={onRetry}
          className="h-14 px-6 rounded-full text-body-large-emphasized bg-theme-primary text-on-theme-primary hover:opacity-90 transition-opacity"
        >
          {RETRY_LABEL}
        </button>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-start gap-3">
      <div className="grid place-items-star min-h-20 w-full">
        {widgetState.status === 'loading' && (
          <div
            role="status"
            className="col-start-1 row-start-1 flex items-center justify-center w-full"
          >
            <span className="sr-only">{RECAPTCHA_MODAL_LOADING_LABEL}</span>
            <div
              aria-hidden="true"
              className="w-full max-w-76 h-20 rounded-lg bg-skeleton-bar motion-safe:animate-pulse"
            />
          </div>
        )}
        <div
          ref={widgetContainerRef}
          data-testid="recaptcha-widget-container"
          className="col-start-1 row-start-1 flex justify-center"
        />
      </div>
      {widgetState.status === 'ready' && widgetState.notice !== null && (
        <p
          role="status"
          className="text-caption text-on-surface-variant text-center"
        >
          {widgetState.notice}
        </p>
      )}
    </div>
  );
}
