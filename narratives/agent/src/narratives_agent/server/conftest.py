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
"""Pytest fixtures shared by the server tests."""

import pytest

from narratives_agent import telemetry


@pytest.fixture(autouse=True)
def skip_telemetry_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevents the application lifespan from configuring telemetry.

    `configure_telemetry` installs a global tracer provider, instruments
    httpx and google-genai, and rewrites environment variables. None of that
    can be undone, so a test that starts the lifespan would otherwise change
    the behavior of every test that runs after it. `telemetry_test.py` tests
    the function itself.
    """
    monkeypatch.setattr(telemetry, "configure_telemetry", lambda: None)
