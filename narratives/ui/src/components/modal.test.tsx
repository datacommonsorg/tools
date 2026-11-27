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
 * @fileoverview Tests for Modal.
 */

import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { Modal } from '@/src/components/modal';

/** Returns the rendered `<dialog>`, open or not. */
const getDialog = (): HTMLDialogElement =>
  screen.getByRole('dialog', { hidden: true }) as HTMLDialogElement;

afterEach(cleanup);

describe('Modal', () => {
  it('opens and closes with the open prop', () => {
    // Test: Controlled open state.
    // Situation: The modal renders closed, then open, then closed again.
    // Expectation: The native dialog's `open` follows the prop, and the
    //   dialog is named by its labelling element.
    const renderModal = (open: boolean) => (
      <Modal open={open} aria-labelledby="title">
        <h2 id="title">Title</h2>
      </Modal>
    );
    const { rerender } = render(renderModal(false));
    expect(getDialog().open).toBe(false);

    rerender(renderModal(true));
    expect(getDialog().open).toBe(true);
    expect(screen.getByRole('dialog', { name: 'Title' })).toBe(getDialog());

    rerender(renderModal(false));
    expect(getDialog().open).toBe(false);
  });

  it('reports a native close to onClose', () => {
    // Test: Dismissible modal.
    // Situation: The open dialog closes (as on Escape or a backdrop click).
    // Expectation: Light dismiss is enabled, and onClose is called once.
    const onClose = vi.fn();
    render(
      <Modal open onClose={onClose} aria-labelledby="title">
        <h2 id="title">Title</h2>
      </Modal>,
    );
    const dialog = getDialog();
    expect(dialog.getAttribute('closedby')).toBe('any');

    dialog.close();
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('does not report a close from the open prop to onClose', () => {
    // Test: Parent-initiated close.
    // Situation: The open dialog is closed by setting `open` to false.
    // Expectation: The dialog closes, and onClose is not called.
    const onClose = vi.fn();
    const renderModal = (open: boolean) => (
      <Modal open={open} onClose={onClose} aria-labelledby="title">
        <h2 id="title">Title</h2>
      </Modal>
    );
    const { rerender } = render(renderModal(true));

    rerender(renderModal(false));
    expect(getDialog().open).toBe(false);
    expect(onClose).not.toHaveBeenCalled();
  });

  it('cannot be dismissed without onClose', () => {
    // Test: Modal with no onClose.
    // Situation: Escape fires `cancel` on the open dialog.
    // Expectation: Light dismiss is disabled and `cancel` is prevented, so
    //   the dialog stays open.
    render(
      <Modal open aria-labelledby="title">
        <h2 id="title">Title</h2>
      </Modal>,
    );
    const dialog = getDialog();
    expect(dialog.getAttribute('closedby')).toBe('none');

    const cancel = new Event('cancel', { cancelable: true });
    fireEvent(dialog, cancel);
    expect(cancel.defaultPrevented).toBe(true);
    expect(dialog.open).toBe(true);
  });

  it('uses the widest width unless one is given', () => {
    // Test: Card width.
    // Situation: One modal uses the default width, another sets its own.
    // Expectation: The default is `max-w-198`; a given width replaces it.
    const { rerender } = render(
      <Modal open aria-labelledby="title">
        <h2 id="title">Title</h2>
      </Modal>,
    );
    expect(getDialog().classList.contains('max-w-198')).toBe(true);

    rerender(
      <Modal open aria-labelledby="title" width="max-w-2xl">
        <h2 id="title">Title</h2>
      </Modal>,
    );
    expect(getDialog().classList.contains('max-w-2xl')).toBe(true);
    expect(getDialog().classList.contains('max-w-198')).toBe(false);
  });
});
