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
 * @fileoverview Tests for RecaptchaModal: portal mounting, loading state,
 * checkbox widget lifecycle, focus trapping, responsive sizing, error recovery,
 * and teardown safety.
 */

import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { RecaptchaModal } from '@/src/components/modal_recaptcha';
import {
  RECAPTCHA_MODAL_CLOSE_LABEL,
  RECAPTCHA_MODAL_EXPIRED_NOTE,
  RECAPTCHA_MODAL_LOAD_ERROR,
  RECAPTCHA_MODAL_LOADING_LABEL,
  RECAPTCHA_MODAL_TITLE,
  RECAPTCHA_MODAL_WIDGET_ERROR,
  RETRY_LABEL,
} from '@/src/config/copy_chat';
import {
  ChatSessionContext,
  type ChatSessionContextValue,
} from '@/src/hooks/chat_session_context';
import type { VerificationModalState } from '@/src/hooks/use_sse_chat';
import type {
  GrecaptchaEnterprise,
  GrecaptchaRenderParameters,
} from '@/src/types/grecaptcha';
import * as recaptchaLoader from '@/src/utils/load_recaptcha';

const createContextValue = (
  overrides: Partial<ChatSessionContextValue> = {},
): ChatSessionContextValue => ({
  turns: [],
  isStreaming: false,
  error: null,
  send: vi.fn(async () => undefined),
  stop: vi.fn(),
  verificationModal: { status: 'closed' },
  completeVerification: vi.fn(),
  cancelVerification: vi.fn(),
  newChat: vi.fn(),
  isDrawerOpen: false,
  toggleDrawer: vi.fn(),
  closeDrawer: vi.fn(),
  ...overrides,
});

const renderModal = (
  verificationModal: VerificationModalState,
  callbacks: {
    completeVerification?: (token: string) => void;
    cancelVerification?: () => void;
  } = {},
) => {
  const completeVerification = callbacks.completeVerification ?? vi.fn();
  const cancelVerification = callbacks.cancelVerification ?? vi.fn();
  const context = createContextValue({
    verificationModal,
    completeVerification,
    cancelVerification,
  });
  const view = render(
    <ChatSessionContext.Provider value={context}>
      <RecaptchaModal />
    </ChatSessionContext.Provider>,
  );
  return { ...view, completeVerification, cancelVerification, context };
};

const createMockEnterprise = () => {
  let capturedParams: GrecaptchaRenderParameters | null = null;
  let nextWidgetId = 10;
  const renderFn = vi.fn(
    (container: HTMLElement, params: GrecaptchaRenderParameters): number => {
      capturedParams = params;
      const iframe = document.createElement('iframe');
      iframe.title = 'reCAPTCHA';
      container.appendChild(iframe);
      nextWidgetId += 1;
      return nextWidgetId;
    },
  );
  const resetFn = vi.fn();
  const enterprise: GrecaptchaEnterprise = {
    ready: vi.fn((callback: () => void) => callback()),
    render: renderFn,
    reset: resetFn,
  };
  return {
    enterprise,
    renderFn,
    resetFn,
    getParams: () => capturedParams,
  };
};

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  recaptchaLoader.resetRecaptchaLoaderForTests();
});

describe('RecaptchaModal', () => {
  it('renders nothing when verificationModal is closed', () => {
    // Test: Closed modal state.
    // Situation: `verificationModal` has status `'closed'`.
    // Expectation: No dialog is mounted and `ensureRecaptchaScript` is not called.
    const loadSpy = vi.spyOn(recaptchaLoader, 'ensureRecaptchaScript');
    renderModal({ status: 'closed' });

    expect(screen.queryByRole('dialog')).toBeNull();
    expect(loadSpy).not.toHaveBeenCalled();
  });

  it('portals to document.body, shows loading status, renders the checkbox widget, and submits the solved token', async () => {
    // Test: Happy path for checkbox verification inside the portaled dialog.
    // Situation: The modal opens while `ensureRecaptchaScript` is pending; once
    //   resolved, the checkbox widget renders and invokes its callback.
    // Expectation: The dialog portals to `document.body` with `data-non-print`,
    //   shows a `role="status"` loading region while pending, invokes
    //   `ensureRecaptchaScript` with no arguments (reading runtime config
    //   internally), omits overflow clipping, and forwards the solved token to
    //   `completeVerification`.
    const mock = createMockEnterprise();
    let resolveScript!: (client: GrecaptchaEnterprise) => void;
    const loadSpy = vi
      .spyOn(recaptchaLoader, 'ensureRecaptchaScript')
      .mockImplementation(
        () =>
          new Promise<GrecaptchaEnterprise>((resolve) => {
            resolveScript = resolve;
          }),
      );

    const { container: renderRoot, completeVerification } = renderModal({
      status: 'open',
      checkboxSiteKey: '6Lc_checkbox_key',
    });

    const dialog = screen.getByRole('dialog', { name: RECAPTCHA_MODAL_TITLE });
    expect(renderRoot.contains(dialog)).toBe(false);
    expect(document.body.contains(dialog)).toBe(true);
    expect(dialog.closest('[data-non-print="true"]')).not.toBeNull();
    expect(dialog.getAttribute('aria-modal')).toBe('true');
    expect(dialog.className).not.toContain('overflow-hidden');
    expect(dialog.className).not.toContain('overflow-clip');
    expect(screen.getByRole('status').textContent).toContain(
      RECAPTCHA_MODAL_LOADING_LABEL,
    );
    expect(loadSpy).toHaveBeenCalledTimes(1);
    expect(loadSpy).toHaveBeenCalledWith();

    await act(async () => {
      resolveScript(mock.enterprise);
    });

    await waitFor(() => {
      expect(mock.renderFn).toHaveBeenCalledTimes(1);
    });
    expect(screen.queryByText(RECAPTCHA_MODAL_LOADING_LABEL)).toBeNull();
    const [widgetContainer, params] = mock.renderFn.mock.calls[0];
    expect(widgetContainer.isConnected).toBe(true);
    expect(params.sitekey).toBe('6Lc_checkbox_key');
    expect(params.size).toBe('normal');

    act(() => {
      mock.getParams()?.callback?.('solved-action-token');
    });
    expect(completeVerification).toHaveBeenCalledWith('solved-action-token');
  });

  it('selects compact widget size when the container is narrower than 304px', async () => {
    // Test: Narrow mobile viewport sizing (for example, 320px WCAG reflow).
    // Situation: The widget host parent reports a clientWidth of 260px (< 304px).
    // Expectation: `enterprise.render` receives `size: 'compact'` so the
    //   checkbox never overflows the modal border.
    const mock = createMockEnterprise();
    vi.spyOn(recaptchaLoader, 'ensureRecaptchaScript').mockResolvedValue(
      mock.enterprise,
    );
    vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockReturnValue(260);

    renderModal({ status: 'open', checkboxSiteKey: '6Lc_checkbox' });

    await waitFor(() => {
      expect(mock.renderFn).toHaveBeenCalledTimes(1);
    });
    expect(mock.renderFn.mock.calls[0][1].size).toBe('compact');
  });

  it('dismisses via close button, Escape, and backdrop click, respects defaultPrevented, and restores focus', async () => {
    // Test: Dismissal controls, Escape defaultPrevented handling, and focus restoration.
    // Situation: A trigger button holds focus when the modal opens.
    // Expectation: Opening focuses the close button without triggering a
    //   tooltip, Escape calls `preventDefault()`, already-prevented Escape
    //   events are ignored, and closing restores focus to the trigger.
    const mock = createMockEnterprise();
    vi.spyOn(recaptchaLoader, 'ensureRecaptchaScript').mockResolvedValue(
      mock.enterprise,
    );
    const cancelVerification = vi.fn();

    const trigger = document.createElement('button');
    trigger.type = 'button';
    trigger.textContent = 'Trigger';
    document.body.appendChild(trigger);
    try {
      trigger.focus();

      const openContext = createContextValue({
        verificationModal: { status: 'open', checkboxSiteKey: '6Lc_checkbox' },
        cancelVerification,
      });
      const { rerender } = render(
        <ChatSessionContext.Provider value={openContext}>
          <RecaptchaModal />
        </ChatSessionContext.Provider>,
      );

      const closeButton = screen.getByRole('button', {
        name: RECAPTCHA_MODAL_CLOSE_LABEL,
      });
      expect(document.activeElement).toBe(closeButton);

      fireEvent.click(closeButton);
      const escapeEvent = new KeyboardEvent('keydown', {
        key: 'Escape',
        bubbles: true,
        cancelable: true,
      });
      document.dispatchEvent(escapeEvent);
      expect(escapeEvent.defaultPrevented).toBe(true);

      const preventedEscape = new KeyboardEvent('keydown', {
        key: 'Escape',
        bubbles: true,
        cancelable: true,
      });
      preventedEscape.preventDefault();
      document.dispatchEvent(preventedEscape);

      const scrim = document.querySelector(
        '[aria-hidden="true"][data-non-print="true"]',
      );
      expect(scrim).not.toBeNull();
      if (scrim) {
        fireEvent.click(scrim);
      }
      expect(cancelVerification).toHaveBeenCalledTimes(3);

      const closedContext = createContextValue({
        verificationModal: { status: 'closed' },
        cancelVerification,
      });
      rerender(
        <ChatSessionContext.Provider value={closedContext}>
          <RecaptchaModal />
        </ChatSessionContext.Provider>,
      );
      expect(document.activeElement).toBe(trigger);
    } finally {
      trigger.remove();
    }
  });

  it('traps Tab and Shift+Tab inside the dialog and leaves focus in external challenge iframes', async () => {
    // Test: Modal keyboard focus trap and challenge iframe exemption.
    // Situation: The modal is in the error state with Close and Retry buttons;
    //   later an external body-level iframe holds focus (simulating Google's
    //   floating image-grid challenge bubble).
    // Expectation: `Shift+Tab` on Close wraps to Retry, `Tab` on Retry wraps to
    //   Close, clicking Retry moves focus back to Close, and `Tab` while an
    //   external iframe is focused does not steal focus away.
    vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    const mock = createMockEnterprise();
    vi.spyOn(recaptchaLoader, 'ensureRecaptchaScript')
      .mockRejectedValueOnce(new Error('Blocked'))
      .mockResolvedValueOnce(mock.enterprise);

    renderModal({ status: 'open', checkboxSiteKey: '6Lc_checkbox' });

    const closeButton = screen.getByRole('button', {
      name: RECAPTCHA_MODAL_CLOSE_LABEL,
    });
    const retryButton = await screen.findByRole('button', {
      name: RETRY_LABEL,
    });

    closeButton.focus();
    fireEvent.keyDown(document, { key: 'Tab', shiftKey: true });
    expect(document.activeElement).toBe(retryButton);

    fireEvent.keyDown(document, { key: 'Tab' });
    expect(document.activeElement).toBe(closeButton);

    // Clicking Retry unmounts the Retry button and returns focus to Close.
    retryButton.focus();
    fireEvent.click(retryButton);
    expect(document.activeElement).toBe(closeButton);

    await waitFor(() => {
      expect(mock.renderFn).toHaveBeenCalledTimes(1);
    });

    // Simulate focus inside Google's external body-level challenge iframe.
    const externalIframe = document.createElement('iframe');
    externalIframe.tabIndex = 0;
    document.body.appendChild(externalIframe);
    try {
      externalIframe.focus();
      const tabEvent = new KeyboardEvent('keydown', {
        key: 'Tab',
        bubbles: true,
        cancelable: true,
      });
      document.dispatchEvent(tabEvent);
      expect(tabEvent.defaultPrevented).toBe(false);
      expect(document.activeElement).toBe(externalIframe);
    } finally {
      externalIframe.remove();
    }
  });

  it('logs a warning and renders a retryable alert on script load failure or synchronous render throw', async () => {
    // Test: Load and render failure diagnostics and recovery on Retry.
    // Situation: First `ensureRecaptchaScript` rejects, Retry hits a
    //   synchronous throw from `enterprise.render`, and the next Retry succeeds.
    // Expectation: Both failures log via `console.warn` and render
    //   `RECAPTCHA_MODAL_LOAD_ERROR` with a Retry button; the third attempt
    //   renders the widget and submits the solved token.
    const warnSpy = vi
      .spyOn(console, 'warn')
      .mockImplementation(() => undefined);
    const mock = createMockEnterprise();
    mock.renderFn.mockImplementationOnce(() => {
      throw new Error('Invalid sitekey');
    });
    const loadSpy = vi
      .spyOn(recaptchaLoader, 'ensureRecaptchaScript')
      .mockRejectedValueOnce(new Error('Blocked by extension'))
      .mockResolvedValue(mock.enterprise);

    const { completeVerification } = renderModal({
      status: 'open',
      checkboxSiteKey: '6Lc_checkbox',
    });

    await waitFor(() => {
      expect(screen.getByRole('alert').textContent).toBe(
        RECAPTCHA_MODAL_LOAD_ERROR,
      );
    });
    expect(warnSpy).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole('button', { name: RETRY_LABEL }));
    await waitFor(() => {
      expect(warnSpy).toHaveBeenCalledTimes(2);
      expect(screen.getByRole('alert').textContent).toBe(
        RECAPTCHA_MODAL_LOAD_ERROR,
      );
    });

    fireEvent.click(screen.getByRole('button', { name: RETRY_LABEL }));
    await waitFor(() => {
      expect(mock.renderFn).toHaveBeenCalledTimes(2);
    });
    expect(loadSpy).toHaveBeenCalledTimes(3);
    expect(screen.queryByRole('alert')).toBeNull();

    act(() => {
      mock.getParams()?.callback?.('retried-token');
    });
    expect(completeVerification).toHaveBeenCalledWith('retried-token');
  });

  it('resets the widget on error-callback or blank token and ignores stale callbacks afterward', async () => {
    // Test: Soft-lock prevention and challenge teardown on widget error.
    // Situation: The checkbox renders, expires once, then triggers
    //   `error-callback` followed by late `expired-callback` and `callback`
    //   invocations; a second test triggers a whitespace-only token in `callback`.
    // Expectation: Expiry resets and displays `RECAPTCHA_MODAL_EXPIRED_NOTE`;
    //   `error-callback` immediately calls `enterprise.reset`, renders
    //   `RECAPTCHA_MODAL_WIDGET_ERROR` + Retry, and suppresses subsequent stale
    //   callbacks so the dialog never soft-locks.
    const mock = createMockEnterprise();
    vi.spyOn(recaptchaLoader, 'ensureRecaptchaScript').mockResolvedValue(
      mock.enterprise,
    );

    const { completeVerification, unmount } = renderModal({
      status: 'open',
      checkboxSiteKey: '6Lc_checkbox',
    });
    await waitFor(() => {
      expect(mock.renderFn).toHaveBeenCalledTimes(1);
    });

    act(() => {
      mock.getParams()?.['expired-callback']?.();
    });
    expect(mock.resetFn).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('status').textContent).toBe(
      RECAPTCHA_MODAL_EXPIRED_NOTE,
    );

    act(() => {
      mock.getParams()?.['error-callback']?.();
    });
    expect(mock.resetFn).toHaveBeenCalledTimes(2);
    expect(screen.getByRole('alert').textContent).toBe(
      RECAPTCHA_MODAL_WIDGET_ERROR,
    );

    // Late callbacks after error-callback must be ignored (no soft-lock).
    act(() => {
      mock.getParams()?.['expired-callback']?.();
      mock.getParams()?.callback?.('late-token');
    });
    expect(screen.getByRole('alert').textContent).toBe(
      RECAPTCHA_MODAL_WIDGET_ERROR,
    );
    expect(screen.getByRole('button', { name: RETRY_LABEL })).toBeTruthy();
    expect(completeVerification).not.toHaveBeenCalled();

    unmount();

    // Blank token in callback also tears down the widget and enters error state.
    const secondMock = createMockEnterprise();
    vi.spyOn(recaptchaLoader, 'ensureRecaptchaScript').mockResolvedValue(
      secondMock.enterprise,
    );
    const secondRender = renderModal({
      status: 'open',
      checkboxSiteKey: '6Lc_checkbox',
    });
    await waitFor(() => {
      expect(secondMock.renderFn).toHaveBeenCalledTimes(1);
    });
    act(() => {
      secondMock.getParams()?.callback?.('   ');
    });
    expect(secondMock.resetFn).toHaveBeenCalledTimes(1);
    expect(secondRender.completeVerification).not.toHaveBeenCalled();
    expect(screen.getByRole('alert').textContent).toBe(
      RECAPTCHA_MODAL_WIDGET_ERROR,
    );
  });

  it('resets error state cleanly when closed and reopened after a load failure', async () => {
    // Test: Reopening the modal after an earlier load failure.
    // Situation: The modal opens and fails to load `enterprise.js`, closes,
    //   and opens again when `enterprise.js` succeeds.
    // Expectation: Reopening mounts a fresh dialog and renders the checkbox
    //   rather than staying stuck on the prior error state.
    vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    const mock = createMockEnterprise();
    vi.spyOn(recaptchaLoader, 'ensureRecaptchaScript')
      .mockRejectedValueOnce(new Error('Network down'))
      .mockResolvedValueOnce(mock.enterprise);

    const { rerender } = render(
      <ChatSessionContext.Provider
        value={createContextValue({
          verificationModal: {
            status: 'open',
            checkboxSiteKey: '6Lc_checkbox',
          },
        })}
      >
        <RecaptchaModal />
      </ChatSessionContext.Provider>,
    );

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeTruthy();
    });

    rerender(
      <ChatSessionContext.Provider
        value={createContextValue({ verificationModal: { status: 'closed' } })}
      >
        <RecaptchaModal />
      </ChatSessionContext.Provider>,
    );

    rerender(
      <ChatSessionContext.Provider
        value={createContextValue({
          verificationModal: {
            status: 'open',
            checkboxSiteKey: '6Lc_checkbox',
          },
        })}
      >
        <RecaptchaModal />
      </ChatSessionContext.Provider>,
    );

    await waitFor(() => {
      expect(mock.renderFn).toHaveBeenCalledTimes(1);
    });
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('ignores late script resolution after unmount', async () => {
    // Test: DOM liveness check when unmounting before script resolution.
    // Situation: Unmount occurs while `ensureRecaptchaScript` is still pending,
    //   and then the script promise resolves.
    // Expectation: `enterprise.render` is never called on the disconnected
    //   container.
    const mock = createMockEnterprise();
    let resolveScript!: (client: GrecaptchaEnterprise) => void;
    vi.spyOn(recaptchaLoader, 'ensureRecaptchaScript').mockImplementation(
      () =>
        new Promise<GrecaptchaEnterprise>((resolve) => {
          resolveScript = resolve;
        }),
    );

    const { unmount } = renderModal({
      status: 'open',
      checkboxSiteKey: '6Lc_checkbox',
    });
    unmount();

    await act(async () => {
      resolveScript(mock.enterprise);
    });

    expect(mock.renderFn).not.toHaveBeenCalled();
  });

  it('resets a rendered widget on unmount and swallows reset errors cleanly', async () => {
    // Test: Rendered widget teardown on unmount.
    // Situation: The checkbox widget renders with a widget ID, and `reset`
    //   throws during teardown when the modal unmounts.
    // Expectation: `enterprise.reset` is called with the rendered widget ID
    //   and teardown completes without throwing.
    const mock = createMockEnterprise();
    mock.resetFn.mockImplementationOnce(() => {
      throw new Error('iframe removed');
    });
    vi.spyOn(recaptchaLoader, 'ensureRecaptchaScript').mockResolvedValue(
      mock.enterprise,
    );

    const { unmount } = renderModal({
      status: 'open',
      checkboxSiteKey: '6Lc_checkbox',
    });
    await waitFor(() => {
      expect(mock.renderFn).toHaveBeenCalledTimes(1);
    });
    const renderedWidgetId = mock.renderFn.mock.results[0].value as number;

    expect(() => unmount()).not.toThrow();
    expect(mock.resetFn).toHaveBeenCalledWith(renderedWidgetId);
  });
});
