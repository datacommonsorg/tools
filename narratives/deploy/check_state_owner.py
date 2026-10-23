#!/usr/bin/env python3
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

"""Refuses to apply when the loaded Terraform state belongs to another instance.

    terraform show -json | python3 deploy/check_state_owner.py <instance>

Every instance shares one module directory, and a deploy points it at that
instance's state. If the wrong state is loaded, Terraform sees resources whose
names no longer match the configuration and replaces them, deleting a live
stack without a warning. TF_DATA_DIR keeps each instance's backend pointer
apart; this check is the second line, and stops the deploy before the destroy.

Each resource the module names "<instance>-<suffix>" reveals which instance
the state belongs to: the "<instance>-app" Cloud Run service, plus the
"-datacommons" and "-data-ingest" resources that older states may still hold.
An empty state (a first deploy) passes. The exit status is one of the `EXIT_*`
constants below.
"""

import json
import sys
from collections.abc import Sequence
from typing import Any

# The state is this deployment's, under the names the module builds now.
EXIT_OK = 0
# The state names a different deployment.
EXIT_FOREIGN_STATE = 1
# The command was called without an instance.
EXIT_USAGE = 2
# The state is this deployment's, but holds a service under a name the module
# has since changed. Applying replaces that service, and its URL.
EXIT_SERVICE_RENAMED = 3

# Resources whose name is always "<instance>-<suffix>". These are what the
# deployment name is recovered from.
_INSTANCE_NAME_SUFFIXES = {
    "google_cloud_run_v2_service": ("-app", "-datacommons"),
    "google_cloud_run_v2_job": ("-data-ingest",),
}

# The suffix the module gives the service now; the others are older.
_CURRENT_SERVICE_SUFFIX = "-app"
_SERVICE_TYPE = "google_cloud_run_v2_service"
_MAX_LISTED_RESOURCES = 12


def _list_managed_resources(state: dict[str, Any]) -> list[dict[str, Any]]:
    """Returns the root module's own resources, without data sources.

    Data sources are reads, not ownership, and are rewritten from the tfvars
    on every run, so they say nothing about who owns this state.
    """
    resources: list[dict[str, Any]] = (
        state.get("values", {}).get("root_module", {}).get("resources", [])
        if state
        else []
    )
    return [
        resource
        for resource in resources
        if not str(resource.get("address", "")).startswith("data.")
    ]


def find_superseded_services(
    state: dict[str, Any], instance: str
) -> list[tuple[str, str]]:
    """Returns this deployment's services under a name no longer built.

    Each is an (address, name) pair. `find_foreign_resources` passes them,
    since they are this instance's. An apply replaces them, and a Cloud Run
    URL follows the service name.
    """
    found: list[tuple[str, str]] = []
    for resource in _list_managed_resources(state):
        if resource.get("type") != _SERVICE_TYPE:
            continue
        name = str((resource.get("values") or {}).get("name", ""))
        for suffix in _INSTANCE_NAME_SUFFIXES[_SERVICE_TYPE]:
            if suffix == _CURRENT_SERVICE_SUFFIX:
                continue
            if name == f"{instance}{suffix}":
                found.append((str(resource.get("address", "")), name))
                break
    return found


def find_foreign_resources(
    state: dict[str, Any], instance: str
) -> list[tuple[str, str, str]]:
    """Returns the resources named for a different deployment.

    Each is an (address, owner, name) triple.
    """
    found: list[tuple[str, str, str]] = []
    for resource in _list_managed_resources(state):
        address = str(resource.get("address", ""))
        suffixes = _INSTANCE_NAME_SUFFIXES.get(resource.get("type", ""))
        if not suffixes:
            continue
        name = str((resource.get("values") or {}).get("name", ""))
        for suffix in suffixes:
            if not name.endswith(suffix):
                continue
            owner = name[: -len(suffix)]
            if owner and owner != instance:
                found.append((address, owner, name))
            break
    return found


def main(argv: Sequence[str]) -> int:
    """Checks the state on stdin against `argv[1]` and returns the status.

    Problems are reported on stderr. The status is one of the `EXIT_*`
    constants.
    """
    if len(argv) < 2:
        print(f"usage: {argv[0]} <instance>", file=sys.stderr)
        return EXIT_USAGE

    instance = argv[1]
    state_json = sys.stdin.read().strip()
    if not state_json:
        return EXIT_OK  # no state yet: a first deploy, nothing to protect
    try:
        state = json.loads(state_json)
    except ValueError:
        # `terraform show -json` produced nothing usable. Do not block a deploy
        # on the guard's own failure to parse.
        print(
            "  (state not parseable; ownership check skipped)", file=sys.stderr
        )
        return EXIT_OK

    foreign = find_foreign_resources(state, instance)
    if not foreign:
        return _report_superseded_services(state, instance)

    print(
        f"  The state loaded for '{instance}' contains resources belonging to "
        f"another deployment:",
        file=sys.stderr,
    )
    for address, owner, name in foreign[:_MAX_LISTED_RESOURCES]:
        print(f"    {address}  -> {owner}   ({name})", file=sys.stderr)
    if len(foreign) > _MAX_LISTED_RESOURCES:
        print(
            f"    ... and {len(foreign) - _MAX_LISTED_RESOURCES} more",
            file=sys.stderr,
        )
    return EXIT_FOREIGN_STATE


def _report_superseded_services(state: dict[str, Any], instance: str) -> int:
    """Reports services the module has since renamed, and returns the status."""
    renamed = find_superseded_services(state, instance)
    if not renamed:
        return EXIT_OK

    print(
        f"  The state for '{instance}' holds a service under a name this "
        f"module no longer builds:",
        file=sys.stderr,
    )
    for address, name in renamed:
        print(f"    {address}  ({name})", file=sys.stderr)
    print(
        f"  The module builds '{instance}{_CURRENT_SERVICE_SUFFIX}' now.",
        file=sys.stderr,
    )
    return EXIT_SERVICE_RENAMED


if __name__ == "__main__":
    sys.exit(main(sys.argv))
