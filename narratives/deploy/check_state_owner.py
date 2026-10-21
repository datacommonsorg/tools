#!/usr/bin/env python3
"""Refuse to apply when the loaded Terraform state belongs to another instance.

    terraform show -json | python3 deploy/check_state_owner.py <instance>

Exits non-zero, with the offending addresses, if any resource in the state
names an instance other than the one being deployed.

Why this exists
---------------
Every instance shares one module directory, and a deploy points it at that
instance's state. If the wrong state is ever loaded, Terraform does not see a
mistake -- it sees resources whose names no longer match the configuration, and
replacing those is exactly its job. It will delete a live stack without a
single warning.

That happened: a `--plan` for one instance ran while another's apply was in
flight, the shared backend pointer was repointed underneath it, and the apply
destroyed the other stack's Cloud Run service, service accounts and uptime
check. TF_DATA_DIR now keeps the pointer per-instance so the race cannot
happen. This is the second line: even if some future path loads the wrong state
anyway, the deploy stops before the destroy instead of after it.

Each resource the module names "<instance>-<suffix>" reveals which instance
the state belongs to: the "<instance>-app" Cloud Run service, plus the
"-datacommons" and "-data-ingest" resources that older states may still hold.
An empty state (a first deploy) passes.

Exit status
-----------
0  the state is this deployment's, under the names the module builds now.
1  the state names a different deployment.
2  usage error.
3  the state is this deployment's, but under a name the module has since
   changed: applying replaces the service and its URL.
"""

import json
import sys

# Resources whose name is always "<instance>-<suffix>". These are what the
# deployment name is recovered from.
_NAMED = {
    "google_cloud_run_v2_service": ("-app", "-datacommons"),
    "google_cloud_run_v2_job": ("-data-ingest",),
}

# The suffix the module gives the service now; the others in _NAMED are older.
_CURRENT_SERVICE_SUFFIX = "-app"
_SERVICE = "google_cloud_run_v2_service"


def _managed(state: dict) -> list:
    """The root module's own resources, with data sources left out.

    Data sources are reads, not ownership, and are rewritten from the tfvars
    on every run -- they say nothing about who owns this state.
    """
    resources = (
        state.get("values", {}).get("root_module", {}).get("resources", [])
        if state
        else []
    )
    return [
        resource
        for resource in resources
        if not str(resource.get("address", "")).startswith("data.")
    ]


def superseded(state: dict, instance: str) -> list:
    """This deployment's services, under a name the module no longer builds.

    `offending` passes them: they are this instance's. An apply replaces
    them, and a Cloud Run URL follows the service name.
    """
    found = []
    for resource in _managed(state):
        if resource.get("type") != _SERVICE:
            continue
        name = str((resource.get("values") or {}).get("name", ""))
        for suffix in _NAMED[_SERVICE]:
            if suffix == _CURRENT_SERVICE_SUFFIX:
                continue
            if name == f"{instance}{suffix}":
                found.append((resource.get("address", ""), name))
                break
    return found


def offending(state: dict, instance: str) -> list:
    """Resources in the state whose name belongs to a different deployment."""
    found = []
    for resource in _managed(state):
        address = resource.get("address", "")
        suffixes = _NAMED.get(resource.get("type", ""))
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


def main(argv) -> int:
    if len(argv) < 2:
        print(f"usage: {argv[0]} <instance>", file=sys.stderr)
        return 2

    instance = argv[1]
    raw = sys.stdin.read().strip()
    if not raw:
        return 0  # no state yet: a first deploy, nothing to protect
    try:
        state = json.loads(raw)
    except ValueError:
        # `terraform show -json` produced nothing usable. Do not block a deploy
        # on the guard's own failure to parse.
        print(
            "  (state not parseable; ownership check skipped)", file=sys.stderr
        )
        return 0

    problems = offending(state, instance)
    if not problems:
        return _report_superseded(state, instance)

    print(
        f"  The state loaded for '{instance}' contains resources belonging to "
        f"another deployment:",
        file=sys.stderr,
    )
    for address, other, detail in problems[:12]:
        print(f"    {address}  -> {other}   ({detail})", file=sys.stderr)
    if len(problems) > 12:
        print(f"    ... and {len(problems) - 12} more", file=sys.stderr)
    return 1


def _report_superseded(state: dict, instance: str) -> int:
    """Reports services the module has since renamed, and returns the status."""
    renamed = superseded(state, instance)
    if not renamed:
        return 0

    print(
        f"  The state for '{instance}' describes a service under a name this "
        f"module no longer builds:",
        file=sys.stderr,
    )
    for address, name in renamed:
        print(f"    {address}  ({name})", file=sys.stderr)
    print(
        f"  It builds '{instance}{_CURRENT_SERVICE_SUFFIX}' now. Applying "
        f"DESTROYS the service above,\n"
        f"  and the URL it answers on, then creates the new one.",
        file=sys.stderr,
    )
    return 3


if __name__ == "__main__":
    sys.exit(main(sys.argv))
