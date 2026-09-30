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

from narratives_agent.settings import get_settings


@pytest.fixture(autouse=True)
def clear_settings_cache() -> Iterator[None]:
    """Clears the cached settings before and after each test.

    `get_settings` reads the environment once and caches the result, so without
    this a test would see the environment of whichever test or import called it
    first rather than the variables it sets itself.
    """
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
