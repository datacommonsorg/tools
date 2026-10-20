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
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied. See the License for the specific language governing
# permissions and limitations under the License.

"""Unit tests for deploy/check_state_owner.py."""

import io
import json
from typing import Any

import check_state_owner
import pytest

INSTANCE = "base-dc"


def service(address: str, name: str) -> dict[str, Any]:
    """Returns one Cloud Run service as `terraform show -json` reports it."""
    return {
        "address": address,
        "type": "google_cloud_run_v2_service",
        "values": {"name": name},
    }


def state(*resources: dict[str, Any]) -> dict[str, Any]:
    """Wraps resources in the root-module envelope the command reads."""
    return {"values": {"root_module": {"resources": list(resources)}}}


def run(monkeypatch: pytest.MonkeyPatch, document: dict[str, Any] | str) -> int:
    """Runs the command over `document` on stdin and returns its status."""
    raw = document if isinstance(document, str) else json.dumps(document)
    monkeypatch.setattr("sys.stdin", io.StringIO(raw))
    return check_state_owner.main(["check_state_owner.py", INSTANCE])


def test_service_under_the_previous_name_is_reported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reports this deployment's service when the module has renamed it."""
    # Test: A state written by an older generation of the module.
    # Situation: The state holds "base-dc-datacommons", the name the module
    #   gave the service before it became "base-dc-app".
    # Expectation: Status 3, so deploy.sh can stop and say the apply would
    #   replace the service and change its URL. The resource belongs to this
    #   deployment, so the ownership check itself finds nothing.
    document = state(
        service("google_cloud_run_v2_service.dc_web", "base-dc-datacommons")
    )

    assert check_state_owner.offending(document, INSTANCE) == []
    assert run(monkeypatch, document) == 3


def test_service_under_the_current_name_passes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Passes a state whose names already match what the module builds."""
    # Test: A state written by the current module.
    # Situation: The state holds "base-dc-app".
    # Expectation: Status 0 -- nothing is renamed, so an apply updates the
    #   service in place.
    document = state(
        service("google_cloud_run_v2_service.dc_app", "base-dc-app")
    )

    assert check_state_owner.superseded(document, INSTANCE) == []
    assert run(monkeypatch, document) == 0


def test_another_deployment_outranks_a_rename(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reports a foreign state even when a renamed service sits beside it."""
    # Test: Both failures present at once.
    # Situation: The state holds this deployment's old "base-dc-datacommons"
    #   and another deployment's "india-app".
    # Expectation: Status 1. The wrong state is the graver fault and the one
    #   with a different remedy, so it must not be masked by the rename.
    document = state(
        service("google_cloud_run_v2_service.dc_web", "base-dc-datacommons"),
        service("google_cloud_run_v2_service.other", "india-app"),
    )

    assert run(monkeypatch, document) == 1


def test_data_sources_are_not_ownership(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ignores a read of a service, which says nothing about who owns it."""
    # Test: A data source carrying a previous-generation name.
    # Situation: The only matching resource is addressed "data.*", which the
    #   tfvars rewrite on every run.
    # Expectation: Status 0, matching how the ownership check reads them.
    document = state(
        service(
            "data.google_cloud_run_v2_service.existing", "base-dc-datacommons"
        )
    )

    assert check_state_owner.superseded(document, INSTANCE) == []
    assert run(monkeypatch, document) == 0


@pytest.mark.parametrize("raw", ["", "   ", "not json"])
def test_unusable_state_never_blocks_a_deploy(
    monkeypatch: pytest.MonkeyPatch, raw: str
) -> None:
    """Passes when there is no state yet, or none that parses."""
    # Test: A first deploy, and a `terraform show` that produced nothing
    #   usable.
    # Situation: stdin is empty, whitespace, or not JSON.
    # Expectation: Status 0 -- the guard does not block a deploy on its own
    #   inability to read the state.
    assert run(monkeypatch, raw) == 0
