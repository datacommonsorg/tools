# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Response classes shared by the agent's routes."""

from starlette.responses import StreamingResponse
from starlette.types import Receive, Scope, Send


class ClosingStreamingResponse(StreamingResponse):
    """A `StreamingResponse` whose background task runs however it ends.

    Starlette runs `background` after a client disconnect only when the server
    reports an ASGI spec version below 2.4, as Uvicorn 0.54 does. From 2.4 on,
    a disconnect surfaces as `ClientDisconnect`, which leaves `__call__`
    before `background` runs. This class runs the task in a `finally` block
    instead, exactly once, so a task that releases a resource runs when the
    stream completes, fails, or is cut off by the client.
    """

    async def __call__(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        background, self.background = self.background, None
        try:
            await super().__call__(scope, receive, send)
        finally:
            if background is not None:
                await background()
