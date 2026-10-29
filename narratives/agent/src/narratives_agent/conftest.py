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
"""Pytest fixtures shared by every test in the agent package."""

from collections.abc import Iterator

import pytest

from narratives_agent.gcp_auth import reset_dc_api_key
from narratives_agent.secret_manager import reset_secret_manager_client
from narratives_agent.settings import (
    DC_API_KEY_ENV,
    DC_API_KEY_SECRET_ENV,
    TRANSCRIPT_HMAC_SECRET_ENV,
    TRANSCRIPT_HMAC_SECRET_NAME_ENV,
    get_settings,
)
from narratives_agent.workflows.transcript import reset_signing_key


@pytest.fixture(autouse=True)
def clear_settings_cache(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Clears cached settings, clients, and keys before and after each test.

    `get_settings`, `_resolve_signing_key`, and `_resolve_dc_api_key` read the
    environment once and cache the result, so without this a test would see the
    environment of whichever test or import called them first rather than the
    variables it sets itself.
    """
    for var in (
        DC_API_KEY_ENV,
        DC_API_KEY_SECRET_ENV,
        "ENABLE_CHAT",
        "K_SERVICE",
        "KUBERNETES_SERVICE_HOST",
        TRANSCRIPT_HMAC_SECRET_ENV,
        TRANSCRIPT_HMAC_SECRET_NAME_ENV,
    ):
        monkeypatch.delenv(var, raising=False)
    get_settings.cache_clear()
    reset_signing_key()
    reset_dc_api_key()
    reset_secret_manager_client()
    yield
    get_settings.cache_clear()
    reset_signing_key()
    reset_dc_api_key()
    reset_secret_manager_client()
