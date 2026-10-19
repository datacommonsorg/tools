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
 * @fileoverview Tests for the desktop rail's chat controls.
 */

import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { ChatSessionProvider } from '@/src/hooks/chat_session_context';
import { Sidebar } from './sidebar';

afterEach(cleanup);

describe('Sidebar', () => {
  it('offers a new chat and no chats list', () => {
    // Test: The controls on the desktop rail.
    // Situation: The rail renders on the Data Agent route.
    // Expectation: Only the new-chat control is offered; there is no control
    //              for a list of saved chats, because chats are not saved.
    render(
      <ChatSessionProvider>
        <Sidebar />
      </ChatSessionProvider>,
    );

    expect(screen.getByRole('button', { name: 'Start new chat' })).toBeTruthy();
    expect(
      screen.queryByRole('button', { name: 'Toggle chats list' }),
    ).toBeNull();
  });
});
