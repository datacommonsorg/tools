#!/usr/bin/env python3
"""Refuse to apply when the loaded Terraform state belongs to another instance.

    terraform show -json | python3 deploy/check-state-owner.py <instance>

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

The check is deliberately conservative. It reads the deployment name back out
of the resources the module always creates -- the two Cloud Run services, named
"<instance>-app" and "<instance>-datacommons" -- and flags only a name that is
not ours. An empty state (a first deploy) and a correct state both pass, and it
needs no list of other deployments to compare against, which is what it used to
require and what this repository no longer has.
"""

import json
import re
import sys


# Resources whose name is always "<instance>-<suffix>". These are what the
# deployment name is recovered from.
_NAMED = {
    "google_cloud_run_v2_service": ("-app", "-datacommons"),
    "google_cloud_run_v2_job": ("-data-ingest",),
}


def offending(state: dict, instance: str) -> list:
    """Resources in the state whose name belongs to a different deployment."""
    resources = (
        state.get("values", {}).get("root_module", {}).get("resources", [])
        if state
        else []
    )

    found = []
    for resource in resources:
        address = resource.get("address", "")
        if address.startswith("data."):
            # Data sources are reads, not ownership, and are rewritten from the
            # tfvars on every run -- they say nothing about who owns this state.
            continue
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
        print("  (state not parseable; ownership check skipped)", file=sys.stderr)
        return 0

    problems = offending(state, instance)
    if not problems:
        return 0

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


if __name__ == "__main__":
    sys.exit(main(sys.argv))
