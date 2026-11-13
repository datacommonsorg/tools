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
"""Adds HTTP security headers to every response the application sends.

`SecurityHeadersMiddleware` is plain ASGI middleware rather than a subclass
of Starlette's `BaseHTTPMiddleware`, which wraps the response body. The
middleware edits only the `http.response.start` message and forwards every
other message as received, so a streamed response such as
`/agent/chat/stream` is never buffered. Starlette's `ServerErrorMiddleware`
wraps every user middleware, so the 500 response that it sends for an
unhandled exception does not carry these headers.
"""

from typing import Final

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

# The middleware sets these headers on every HTTP response that does not
# already carry them:
# - `X-Content-Type-Options` stops browsers from guessing a content type.
# - `X-Frame-Options` lets only this origin frame the pages.
# - `Referrer-Policy` makes the browser send other origins only the page's
#   origin, never its path.
# - `Cross-Origin-Opener-Policy` isolates the browsing context from other
#   origins while keeping popups, such as links opened in a new tab, usable.
SECURITY_HEADERS: Final[tuple[tuple[str, str], ...]] = (
    ("X-Content-Type-Options", "nosniff"),
    ("X-Frame-Options", "SAMEORIGIN"),
    ("Referrer-Policy", "strict-origin-when-cross-origin"),
    ("Cross-Origin-Opener-Policy", "same-origin-allow-popups"),
)


class SecurityHeadersMiddleware:
    """Adds `SECURITY_HEADERS` to every HTTP response.

    A header the response already carries keeps its value. The middleware
    sets no `Content-Security-Policy`, so the policies that routes set, such
    as `sandbox` on SVG files, reach the browser unchanged.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        """Serves `scope` with the security headers added to its response.

        Scopes other than HTTP, such as the lifespan, pass through unchanged.
        """
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_security_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                message.setdefault("headers", [])
                headers = MutableHeaders(scope=message)
                for name, value in SECURITY_HEADERS:
                    if name not in headers:
                        headers.append(name, value)
            await send(message)

        await self.app(scope, receive, send_with_security_headers)
