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

import { X } from 'lucide-react';
import { useCallback, useEffect, useId, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import {
  RECAPTCHA_MODAL_CLOSE_LABEL,
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
  if (!dialog.contains(active)) {
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
  const closeButtonRef = useRef<HTMLButtonElement | null>(null);
  const descriptionId = useId();
  const [renderAttempt, setRenderAttempt] = useState(0);

  const handleRetry = useCallback(() => {
    setRenderAttempt((attempt) => attempt + 1);
    // Keep focus inside the dialog as the Retry button unmounts.
    closeButtonRef.current?.focus();
  }, []);

  // Move focus into the dialog on mount and restore it to the prior control
  // on unmount, decoupled from callback identity changes.
  useEffect(() => {
    const previouslyFocused =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    closeButtonRef.current?.focus();

    return () => {
      if (previouslyFocused?.isConnected) {
        previouslyFocused.focus();
      }
    };
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
      {/* Pointer-only backdrop; Escape and the close button serve the keyboard. */}
      <div
        data-non-print="true"
        className="fixed inset-0 z-50 bg-scrim/30"
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
          className="pointer-events-auto w-full max-w-sm bg-surface rounded-card border border-outline shadow-elevated p-4 sm:p-6 motion-safe:animate-fade-in"
        >
          <div className="flex items-start justify-between gap-3">
            <h2
              id={titleId}
              className="text-section-heading text-on-surface pt-1"
            >
              {RECAPTCHA_MODAL_TITLE}
            </h2>
            <button
              ref={closeButtonRef}
              type="button"
              aria-label={RECAPTCHA_MODAL_CLOSE_LABEL}
              onClick={onCancel}
              className="w-11 h-11 -mr-2 -mt-2 flex items-center justify-center rounded-full text-subtle hover:bg-button-hover transition-colors shrink-0"
            >
              <X strokeWidth={1.5} aria-hidden="true" />
            </button>
          </div>

          <p
            id={descriptionId}
            className="mt-2 text-body-medium text-on-surface-variant"
          >
            {RECAPTCHA_MODAL_DESCRIPTION}
          </p>

          <div className="mt-5">
            <RecaptchaCheckboxWidget
              key={renderAttempt}
              checkboxSiteKey={checkboxSiteKey}
              onComplete={onComplete}
              onRetry={handleRetry}
            />
          </div>
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
      if (enterpriseClient !== null && activeWidgetId !== null) {
        try {
          enterpriseClient.reset(activeWidgetId);
        } catch {
          // Ignore reset failures if the iframe was already torn down.
        }
      }
      container.replaceChildren();
    };

    void ensureRecaptchaScript().then(
      (enterprise) => {
        if (!isActive || !container.isConnected) return;
        enterpriseClient = enterprise;
        // Clear any leftover nodes so StrictMode double-effects never hit
        // "reCAPTCHA has already been rendered in this element".
        container.replaceChildren();
        const availableWidth =
          container.parentElement?.clientWidth ?? container.clientWidth;
        const size: GrecaptchaSize =
          availableWidth > 0 && availableWidth < NORMAL_WIDGET_WIDTH_PX
            ? 'compact'
            : 'normal';
        try {
          widgetId = enterprise.render(container, {
            sitekey: checkboxSiteKey,
            size,
            callback: (token: string) => {
              if (!isActive) return;
              if (token.trim() === '') {
                teardownWidget();
                setWidgetState({
                  status: 'error',
                  message: RECAPTCHA_MODAL_WIDGET_ERROR,
                });
                return;
              }
              isActive = false;
              onComplete(token);
            },
            'expired-callback': () => {
              if (!isActive) return;
              if (widgetId !== null) {
                try {
                  enterprise.reset(widgetId);
                } catch {
                  // Ignore reset failures if the iframe was already torn down.
                }
              }
              setWidgetState({
                status: 'ready',
                notice: RECAPTCHA_MODAL_EXPIRED_NOTE,
              });
            },
            'error-callback': () => {
              if (!isActive) return;
              teardownWidget();
              setWidgetState({
                status: 'error',
                message: RECAPTCHA_MODAL_WIDGET_ERROR,
              });
            },
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
      },
      (error: unknown) => {
        if (!isActive) return;
        console.warn('[recaptcha] Failed to load enterprise.js:', error);
        teardownWidget();
        setWidgetState({
          status: 'error',
          message: RECAPTCHA_MODAL_LOAD_ERROR,
        });
      },
    );

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
          className="min-h-11 px-4 rounded-full bg-theme-container text-on-theme-container text-label-large hover:opacity-90 transition-opacity"
        >
          {RETRY_LABEL}
        </button>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center gap-3">
      <div className="grid place-items-center min-h-20 w-full">
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
