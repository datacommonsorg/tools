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

import pytest

import check_state_owner

INSTANCE = "base-dc"


def service(address: str, name: str) -> dict[str, Any]:
    """Returns one Cloud Run service as `terraform show -json` reports it."""
    return {
        "address": address,
        "type": "google_cloud_run_v2_service",
        "values": {"name": name},
    }


def job(address: str, name: str) -> dict[str, Any]:
    """Returns one Cloud Run job as `terraform show -json` reports it."""
    return {
        "address": address,
        "type": "google_cloud_run_v2_job",
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
    # Expectation: The renamed status, and the ownership check itself finds
    #   nothing.
    document = state(
        service("google_cloud_run_v2_service.dc_web", "base-dc-datacommons")
    )

    assert check_state_owner.find_foreign_resources(document, INSTANCE) == []
    assert run(monkeypatch, document) == check_state_owner.EXIT_SERVICE_RENAMED


def test_service_under_the_current_name_passes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Passes a state whose names already match what the module builds."""
    # Test: A state written by the current module.
    # Situation: The state holds "base-dc-app".
    # Expectation: Status OK -- nothing is renamed, so an apply updates the
    #   service in place.
    document = state(
        service("google_cloud_run_v2_service.dc_app", "base-dc-app")
    )

    assert check_state_owner.find_superseded_services(document, INSTANCE) == []
    assert run(monkeypatch, document) == check_state_owner.EXIT_OK


def test_another_deployment_outranks_a_rename(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reports a foreign state even when a renamed service sits beside it."""
    # Test: Both failures present at once.
    # Situation: The state holds this deployment's old "base-dc-datacommons"
    #   and another deployment's "india-app".
    # Expectation: The foreign-state status -- the wrong state has a different
    #   remedy, so the rename must not mask it.
    document = state(
        service("google_cloud_run_v2_service.dc_web", "base-dc-datacommons"),
        service("google_cloud_run_v2_service.other", "india-app"),
    )

    assert run(monkeypatch, document) == check_state_owner.EXIT_FOREIGN_STATE


def test_rename_report_names_the_service_and_no_mode(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Reports a renamed service in words that suit a deploy and a destroy."""
    # Test: The message printed for a renamed service.
    # Situation: The state holds "base-dc-datacommons".
    # Expectation: stderr names the old service and the name the module builds
    #   now, and says nothing about applying, since --destroy prints it too.
    document = state(
        service("google_cloud_run_v2_service.dc_web", "base-dc-datacommons")
    )

    run(monkeypatch, document)

    report = capsys.readouterr().err
    assert "google_cloud_run_v2_service.dc_web  (base-dc-datacommons)" in report
    assert "'base-dc-app'" in report
    assert "apply" not in report.lower()


def test_job_owned_by_this_deployment_passes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Passes a state whose ingest job is named for this deployment."""
    # Test: Ownership read from a Cloud Run job.
    # Situation: The only named resource is the "base-dc-data-ingest" job.
    # Expectation: Status OK.
    document = state(
        job("google_cloud_run_v2_job.data_ingest", "base-dc-data-ingest")
    )

    assert run(monkeypatch, document) == check_state_owner.EXIT_OK


def test_job_owned_by_another_deployment_is_reported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reports a state whose ingest job is named for another deployment."""
    # Test: A foreign state found through a Cloud Run job.
    # Situation: The only named resource is the "india-data-ingest" job.
    # Expectation: The foreign-state status, with the job's owner recovered.
    document = state(
        job("google_cloud_run_v2_job.data_ingest", "india-data-ingest")
    )

    assert check_state_owner.find_foreign_resources(document, INSTANCE) == [
        ("google_cloud_run_v2_job.data_ingest", "india", "india-data-ingest")
    ]
    assert run(monkeypatch, document) == check_state_owner.EXIT_FOREIGN_STATE


def test_data_sources_are_not_ownership(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ignores a read of a service, which says nothing about who owns it."""
    # Test: A data source carrying a previous-generation name.
    # Situation: The only matching resource is addressed "data.*", which the
    #   tfvars rewrite on every run.
    # Expectation: Status OK, matching how the ownership check reads them.
    document = state(
        service(
            "data.google_cloud_run_v2_service.existing", "base-dc-datacommons"
        )
    )

    assert check_state_owner.find_superseded_services(document, INSTANCE) == []
    assert run(monkeypatch, document) == check_state_owner.EXIT_OK


@pytest.mark.parametrize("raw", ["", "   ", "not json"])
def test_unusable_state_never_blocks_a_deploy(
    monkeypatch: pytest.MonkeyPatch, raw: str
) -> None:
    """Passes when there is no state yet, or none that parses."""
    # Test: A first deploy, and a `terraform show` that produced nothing
    #   usable.
    # Situation: stdin is empty, whitespace, or not JSON.
    # Expectation: Status OK -- the guard does not block on its own failure to
    #   read the state.
    assert run(monkeypatch, raw) == check_state_owner.EXIT_OK


def test_missing_instance_is_a_usage_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rejects a call that names no instance, before reading any state."""
    # Test: The command run without its argument.
    # Situation: argv holds only the script name.
    # Expectation: The usage status, whatever stdin holds.
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(state())))

    status = check_state_owner.main(["check_state_owner.py"])

    assert status == check_state_owner.EXIT_USAGE
