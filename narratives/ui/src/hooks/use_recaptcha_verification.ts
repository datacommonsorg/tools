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
 * @fileoverview Manages the fallback reCAPTCHA checkbox verification modal
 * state machine and in-memory action-token cache used by `useSseChat`.
 */

import { useCallback, useEffect, useRef, useState } from 'react';

/**
 * In-memory lifetime of a checkbox reCAPTCHA action token (25 minutes),
 * keeping a 5-minute margin inside Cloud Armor's 30-minute validity window.
 */
export const RECAPTCHA_ACTION_TOKEN_TTL_MS = 25 * 60 * 1000;

/** Modal state for fallback checkbox reCAPTCHA verification. */
export type VerificationModalState =
  | { status: 'closed' }
  | { status: 'open'; checkboxSiteKey: string };

/** Outcome of awaiting user resolution of {@link VerificationModalState}. */
export type VerificationOutcome =
  | { status: 'verified'; token: string }
  | { status: 'canceled' }
  | { status: 'aborted' };

/** Cached checkbox reCAPTCHA token with its expiration timestamp in epoch ms. */
interface CachedActionToken {
  token: string;
  expiresAtMs: number;
}

/** Pending promise resolver for an active verification modal prompt. */
interface PendingVerification {
  resolve: (outcome: VerificationOutcome) => void;
}

/** Closed sentinel reused to avoid unnecessary state object churn. */
const CLOSED_VERIFICATION_MODAL: VerificationModalState = { status: 'closed' };

/** Public surface of {@link useRecaptchaVerification}. */
export interface UseRecaptchaVerificationResult {
  verificationModal: VerificationModalState;
  /** Returns the cached checkbox token while within its TTL, else `null`. */
  getActiveToken: () => string | null;
  /** Evicts any cached checkbox token (for example, after an HTTP 403). */
  clearToken: () => void;
  /** Opens the modal and resolves when verified, canceled, or aborted. */
  requestVerification: (
    checkboxSiteKey: string,
  ) => Promise<VerificationOutcome>;
  /** Closes any open modal and settles its awaiting caller as `'aborted'`. */
  abortVerification: () => void;
  /** Caches the solved token, closes the modal, and resolves as `'verified'`. */
  completeVerification: (token: string) => void;
  /** Closes the modal and resolves its awaiting caller as `'canceled'`. */
  cancelVerification: () => void;
}

/**
 * Coordinates the fallback reCAPTCHA checkbox modal lifecycle and caches the
 * latest solved action token in memory for {@link RECAPTCHA_ACTION_TOKEN_TTL_MS}.
 */
export function useRecaptchaVerification(): UseRecaptchaVerificationResult {
  const [verificationModal, setVerificationModal] =
    useState<VerificationModalState>(CLOSED_VERIFICATION_MODAL);
  const actionTokenRef = useRef<CachedActionToken | null>(null);
  const pendingVerificationRef = useRef<PendingVerification | null>(null);

  const settlePending = useCallback((outcome: VerificationOutcome) => {
    const pending = pendingVerificationRef.current;
    pendingVerificationRef.current = null;
    setVerificationModal(CLOSED_VERIFICATION_MODAL);
    pending?.resolve(outcome);
  }, []);

  const getActiveToken = useCallback((): string | null => {
    const cached = actionTokenRef.current;
    if (!cached) return null;
    if (Date.now() >= cached.expiresAtMs) {
      actionTokenRef.current = null;
      return null;
    }
    return cached.token;
  }, []);

  const clearToken = useCallback(() => {
    actionTokenRef.current = null;
  }, []);

  const requestVerification = useCallback(
    (checkboxSiteKey: string): Promise<VerificationOutcome> =>
      new Promise<VerificationOutcome>((resolve) => {
        // Abort any superseded verification waiter before replacing it.
        const previous = pendingVerificationRef.current;
        pendingVerificationRef.current = { resolve };
        previous?.resolve({ status: 'aborted' });
        setVerificationModal({ status: 'open', checkboxSiteKey });
      }),
    [],
  );

  const abortVerification = useCallback(() => {
    settlePending({ status: 'aborted' });
  }, [settlePending]);

  const completeVerification = useCallback(
    (token: string) => {
      const trimmed = token.trim();
      if (trimmed === '' || !pendingVerificationRef.current) return;
      actionTokenRef.current = {
        token: trimmed,
        expiresAtMs: Date.now() + RECAPTCHA_ACTION_TOKEN_TTL_MS,
      };
      settlePending({ status: 'verified', token: trimmed });
    },
    [settlePending],
  );

  const cancelVerification = useCallback(() => {
    settlePending({ status: 'canceled' });
  }, [settlePending]);

  // Resolve any awaiting promise on unmount so suspended callers do not dangle.
  useEffect(() => {
    return () => {
      const pending = pendingVerificationRef.current;
      pendingVerificationRef.current = null;
      pending?.resolve({ status: 'aborted' });
    };
  }, []);

  return {
    verificationModal,
    getActiveToken,
    clearToken,
    requestVerification,
    abortVerification,
    completeVerification,
    cancelVerification,
  };
}
