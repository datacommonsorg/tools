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
"""Tests for the Secret Manager client and cached secret resolution."""

import threading

import pytest

from narratives_agent import secret_manager


def test_fetch_secret_resolves_names_and_strips(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: Name resolution and whitespace stripping in `fetch_secret`.
    # Situation: A short secret ID, an unversioned full resource path, and a
    #   fully versioned path are fetched with surrounding whitespace.
    # Expectation: The short name resolves to
    #   `projects/{project}/secrets/{name}/versions/latest`, the unversioned
    #   path appends `/versions/latest`, the versioned path is preserved, and
    #   whitespace is stripped.
    requested_names: list[str] = []

    class _StubPayload:
        data = b"  secret-value-123\n"

    class _StubVersionResponse:
        payload = _StubPayload()

    class _StubSecretClient:
        def access_secret_version(
            self, request: dict[str, str], timeout: float
        ) -> _StubVersionResponse:
            requested_names.append(request["name"])
            return _StubVersionResponse()

    class _StubSecretModule:
        SecretManagerServiceClient = _StubSecretClient

    monkeypatch.setattr(secret_manager, "_SECRET_MANAGER_AVAILABLE", True)
    monkeypatch.setattr(
        secret_manager, "secretmanager", _StubSecretModule, raising=False
    )
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "my-project")
    secret_manager.reset_secret_manager_client()

    val1 = secret_manager.fetch_secret("  my-secret/  ", "MY_ENV_VAR")
    assert val1 == "secret-value-123"
    assert (
        requested_names[0]
        == "projects/my-project/secrets/my-secret/versions/latest"
    )

    val2 = secret_manager.fetch_secret(
        "projects/other-proj/secrets/other-secret/ ", "OTHER_VAR"
    )
    assert val2 == "secret-value-123"
    assert (
        requested_names[1]
        == "projects/other-proj/secrets/other-secret/versions/latest"
    )

    val3 = secret_manager.fetch_secret(
        "projects/other-proj/secrets/other-secret/versions/2", "VERSIONED_VAR"
    )
    assert val3 == "secret-value-123"
    assert (
        requested_names[2]
        == "projects/other-proj/secrets/other-secret/versions/2"
    )


def test_fetch_secret_empty_name_returns_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: Blank or empty secret names return empty without API calls.
    # Situation: `fetch_secret` is called with empty or whitespace-only names.
    # Expectation: Empty string is returned.
    monkeypatch.setattr(secret_manager, "_SECRET_MANAGER_AVAILABLE", True)
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "my-project")
    secret_manager.reset_secret_manager_client()

    assert secret_manager.fetch_secret("", "MY_VAR") == ""
    assert secret_manager.fetch_secret("   ", "MY_VAR") == ""


def test_fetch_secret_short_name_requires_project(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: Short secret IDs require `GOOGLE_CLOUD_PROJECT`.
    # Situation: A short secret name is requested but `GOOGLE_CLOUD_PROJECT` is
    #   unset.
    # Expectation: `fetch_secret` returns an empty string without making any
    #   client calls.
    monkeypatch.setattr(secret_manager, "_SECRET_MANAGER_AVAILABLE", True)
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    secret_manager.reset_secret_manager_client()

    assert secret_manager.fetch_secret("short-name", "MY_VAR") == ""


def test_fetch_secret_handles_client_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: Error handling in `fetch_secret`.
    # Situation: Secret Manager client raises an error or is unavailable.
    # Expectation: `fetch_secret` returns an empty string without re-raising the
    #   exception.
    class _ErrorClient:
        def access_secret_version(
            self, request: dict[str, str], timeout: float
        ) -> None:
            raise RuntimeError("API error")

    class _StubSecretModule:
        SecretManagerServiceClient = _ErrorClient

    monkeypatch.setattr(secret_manager, "_SECRET_MANAGER_AVAILABLE", True)
    monkeypatch.setattr(
        secret_manager, "secretmanager", _StubSecretModule, raising=False
    )
    secret_manager.reset_secret_manager_client()

    assert (
        secret_manager.fetch_secret("projects/p/secrets/s/versions/1", "MY_VAR")
        == ""
    )

    monkeypatch.setattr(secret_manager, "_SECRET_MANAGER_AVAILABLE", False)
    assert (
        secret_manager.fetch_secret("projects/p/secrets/s/versions/1", "MY_VAR")
        == ""
    )


def test_fetch_secret_with_ttl_caches_and_expires(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: In-memory TTL caching in `fetch_secret_with_ttl`.
    # Situation: Multiple calls request the same secret, first within TTL and
    #   then after TTL expiration.
    # Expectation: Cached value is returned on subsequent calls within TTL
    #   without refetching; once TTL expires, `fetch_secret` is called again.
    call_count = 0

    def _stub_fetch(name: str, var: str) -> str:
        nonlocal call_count
        call_count += 1
        return f"value-{call_count}"

    monkeypatch.setattr(secret_manager, "fetch_secret", _stub_fetch)
    secret_manager.reset_secret_manager_client()

    # Initial fetch
    val1 = secret_manager.fetch_secret_with_ttl(
        "my-secret", "VAR", ttl_seconds=10.0
    )
    assert val1 == "value-1"
    assert call_count == 1

    # Immediate second call uses cache
    val2 = secret_manager.fetch_secret_with_ttl(
        "my-secret", "VAR", ttl_seconds=10.0
    )
    assert val2 == "value-1"
    assert call_count == 1

    # Fast-forward cached timestamp past TTL
    cached = secret_manager._secret_manager_cache["my-secret"]
    secret_manager._secret_manager_cache["my-secret"] = (
        cached[0] - 20.0,
        cached[1],
    )

    # Call after expiry refetches
    val3 = secret_manager.fetch_secret_with_ttl(
        "my-secret", "VAR", ttl_seconds=10.0
    )
    assert val3 == "value-2"
    assert call_count == 2


class _SignalingSecretCache(dict[str, tuple[float, str]]):
    """Secret cache that sets an event when a lookup returns no entry."""

    def __init__(self) -> None:
        super().__init__()
        self.missed = threading.Event()

    def get(  # type: ignore[override]
        self, key: str, default: tuple[float, str] | None = None
    ) -> tuple[float, str] | None:
        value = super().get(key, default)
        if value is None:
            self.missed.set()
        return value


def test_a_waiting_thread_reuses_the_key_loaded_while_it_waited(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test: Concurrent cache misses share one Secret Manager request.
    # Situation: The test holds `_secret_manager_lock` as if another thread
    #   were loading the key. A worker thread misses the empty cache and waits
    #   on the lock; the test then stores a key, as the loading thread would,
    #   and releases the lock.
    # Expectation: The worker returns the stored key without creating a
    #   Secret Manager client itself.
    clients: list[object] = []

    class _StubSecretModule:
        @staticmethod
        def SecretManagerServiceClient() -> object:  # noqa: N802
            clients.append(object())
            raise AssertionError("Secret Manager must not be called")

    secret_path = "projects/test-proj/secrets/gemini-key/versions/latest"
    cache = _SignalingSecretCache()
    monkeypatch.setattr(secret_manager, "_SECRET_MANAGER_AVAILABLE", True)
    monkeypatch.setattr(
        secret_manager, "secretmanager", _StubSecretModule, raising=False
    )
    monkeypatch.setattr(secret_manager, "_secret_manager_cache", cache)
    result: list[str] = []

    with secret_manager._secret_manager_lock:
        worker = threading.Thread(
            target=lambda: result.append(
                secret_manager.fetch_secret_with_ttl(secret_path, "TEST_VAR")
            )
        )
        worker.start()
        assert cache.missed.wait(timeout=5)
        cache[secret_path] = (float("inf"), "loaded-key")
    worker.join(timeout=5)

    assert result == ["loaded-key"]
    assert clients == []
