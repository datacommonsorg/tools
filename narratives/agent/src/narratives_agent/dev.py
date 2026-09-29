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
"""Runs the agent for local development as `uv run narratives-agent-dev`."""

import uvicorn

from narratives_agent.settings import get_settings


def main() -> None:
    """Serves the container's application on 127.0.0.1 with auto-reload.

    The port is AGENT_PORT, 5001 by default.
    """
    uvicorn.run(
        "narratives_agent.server.app:app",
        host="127.0.0.1",
        port=get_settings().agent_port,
        reload=True,
    )
