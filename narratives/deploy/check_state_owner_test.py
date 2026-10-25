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
import re
from pathlib import Path
from typing import Any

import pytest

import check_state_owner

INSTANCE = "this-deployment"


def build_service(address: str, name: str) -> dict[str, Any]:
    """Returns one Cloud Run service as `terraform show -json` reports it."""
    return {
        "address": address,
        "type": "google_cloud_run_v2_service",
        "values": {"name": name},
    }


def build_job(address: str, name: str) -> dict[str, Any]:
    """Returns one Cloud Run job as `terraform show -json` reports it."""
    return {
        "address": address,
        "type": "google_cloud_run_v2_job",
        "values": {"name": name},
    }


def build_state(*resources: dict[str, Any]) -> dict[str, Any]:
    """Wraps resources in the root-module envelope the command reads."""
    return {"values": {"root_module": {"resources": list(resources)}}}


def run_check(
    monkeypatch: pytest.MonkeyPatch, document: dict[str, Any] | str
) -> int:
    """Runs the command over `document` on stdin and returns its status."""
    raw = document if isinstance(document, str) else json.dumps(document)
    monkeypatch.setattr("sys.stdin", io.StringIO(raw))
    return check_state_owner.main(["check_state_owner.py", INSTANCE])


def test_service_under_the_previous_name_is_reported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reports this deployment's service when the module has renamed it."""
    # Test: A state written by an older generation of the module.
    # Situation: The state holds "this-deployment-datacommons", the name the
    #   module gave the service before it became "this-deployment-app".
    # Expectation: The renamed status, and the ownership check itself finds
    #   nothing.
    document = build_state(
        build_service(
            "google_cloud_run_v2_service.dc_web", "this-deployment-datacommons"
        )
    )

    assert check_state_owner.find_foreign_resources(document, INSTANCE) == []
    assert (
        run_check(monkeypatch, document)
        == check_state_owner.EXIT_SERVICE_RENAMED
    )


def test_service_under_the_current_name_passes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Passes a state whose names already match what the module builds."""
    # Test: A state written by the current module.
    # Situation: The state holds "this-deployment-app".
    # Expectation: Status OK -- nothing is renamed, so an apply updates the
    #   service in place.
    document = build_state(
        build_service(
            "google_cloud_run_v2_service.dc_app", "this-deployment-app"
        )
    )

    assert check_state_owner.find_superseded_services(document, INSTANCE) == []
    assert run_check(monkeypatch, document) == check_state_owner.EXIT_OK


def test_another_deployment_outranks_a_rename(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reports a foreign state even when a renamed service sits beside it."""
    # Test: Both failures present at once.
    # Situation: The state holds this deployment's old
    #   "this-deployment-datacommons" and another deployment's
    #   "other-deployment-app".
    # Expectation: The foreign-state status -- the wrong state has a different
    #   remedy, so the rename must not mask it.
    document = build_state(
        build_service(
            "google_cloud_run_v2_service.dc_web", "this-deployment-datacommons"
        ),
        build_service(
            "google_cloud_run_v2_service.other", "other-deployment-app"
        ),
    )

    assert (
        run_check(monkeypatch, document) == check_state_owner.EXIT_FOREIGN_STATE
    )


def test_rename_report_suits_deploy_and_destroy(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Reports a renamed service in words that suit a deploy and a destroy."""
    # Test: The message printed for a renamed service.
    # Situation: The state holds "this-deployment-datacommons".
    # Expectation: stderr names the old service and the name the module builds
    #   now, and says nothing about applying, since --destroy prints it too.
    document = build_state(
        build_service(
            "google_cloud_run_v2_service.dc_web", "this-deployment-datacommons"
        )
    )

    run_check(monkeypatch, document)

    report = capsys.readouterr().err
    assert (
        "google_cloud_run_v2_service.dc_web  (this-deployment-datacommons)"
        in report
    )
    assert "'this-deployment-app'" in report
    assert "apply" not in report.lower()


def test_job_owned_by_this_deployment_passes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Passes a state whose ingest job is named for this deployment."""
    # Test: Ownership read from a Cloud Run job.
    # Situation: The only named resource is the
    #   "this-deployment-data-ingest" job.
    # Expectation: Status OK.
    document = build_state(
        build_job(
            "google_cloud_run_v2_job.data_ingest", "this-deployment-data-ingest"
        )
    )

    assert run_check(monkeypatch, document) == check_state_owner.EXIT_OK


def test_job_owned_by_another_deployment_is_reported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reports a state whose ingest job is named for another deployment."""
    # Test: A foreign state found through a Cloud Run job.
    # Situation: The only named resource is the
    #   "other-deployment-data-ingest" job.
    # Expectation: The foreign-state status, with the job's owner recovered.
    document = build_state(
        build_job(
            "google_cloud_run_v2_job.data_ingest",
            "other-deployment-data-ingest",
        )
    )

    assert check_state_owner.find_foreign_resources(document, INSTANCE) == [
        (
            "google_cloud_run_v2_job.data_ingest",
            "other-deployment",
            "other-deployment-data-ingest",
        )
    ]
    assert (
        run_check(monkeypatch, document) == check_state_owner.EXIT_FOREIGN_STATE
    )


def test_data_sources_are_not_ownership(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ignores a read of a service, which says nothing about who owns it."""
    # Test: A data source carrying a previous-generation name.
    # Situation: The only matching resource is addressed "data.*", which the
    #   tfvars rewrite on every run.
    # Expectation: Status OK, matching how the ownership check reads them.
    document = build_state(
        build_service(
            "data.google_cloud_run_v2_service.existing",
            "this-deployment-datacommons",
        )
    )

    assert check_state_owner.find_superseded_services(document, INSTANCE) == []
    assert run_check(monkeypatch, document) == check_state_owner.EXIT_OK


@pytest.mark.parametrize("raw", ["", "   ", "not json"])
def test_unusable_state_never_blocks_a_deploy(
    monkeypatch: pytest.MonkeyPatch, raw: str
) -> None:
    """Passes when the input holds no state that parses."""
    # Test: A `terraform show` that produced nothing usable.
    # Situation: stdin is empty, whitespace, or not JSON.
    # Expectation: Status OK -- the guard does not block on its own failure to
    #   read the state.
    assert run_check(monkeypatch, raw) == check_state_owner.EXIT_OK


def test_first_deploy_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Passes the empty state `terraform show -json` prints before a deploy."""
    # Test: A first deploy.
    # Situation: The backend holds no state yet, so the input is the empty
    #   state document.
    # Expectation: Status OK.
    assert run_check(monkeypatch, {"format_version": "1.0"}) == (
        check_state_owner.EXIT_OK
    )


@pytest.mark.parametrize(
    "argv",
    [
        ["check_state_owner.py"],
        ["check_state_owner.py", INSTANCE, "unexpected"],
    ],
)
def test_wrong_argument_count_is_a_usage_error(
    monkeypatch: pytest.MonkeyPatch, argv: list[str]
) -> None:
    """Rejects a call that does not name exactly one instance."""
    # Test: The command run with too few or too many arguments.
    # Situation: argv holds only the script name, or an extra argument.
    # Expectation: The usage status, whatever stdin holds.
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(build_state())))

    assert check_state_owner.main(argv) == check_state_owner.EXIT_USAGE


def test_deploy_script_names_the_renamed_status() -> None:
    """Keeps deploy.sh's copy of the renamed status equal to this one."""
    # Test: The status shared between this module and deploy.sh.
    # Situation: deploy.sh defines STATE_SERVICE_RENAMED for itself and for
    #   destroy.sh.
    # Expectation: It equals EXIT_SERVICE_RENAMED.
    deploy_script = Path(check_state_owner.__file__).parent.parent / "deploy.sh"

    match = re.search(
        r"(?m)^STATE_SERVICE_RENAMED=(\d+)$",
        deploy_script.read_text(encoding="utf-8"),
    )

    assert match is not None
    assert int(match.group(1)) == check_state_owner.EXIT_SERVICE_RENAMED
