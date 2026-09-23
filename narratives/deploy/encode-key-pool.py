#!/usr/bin/env python3
"""Turn the supplied Gemini key value into the JSON array the agent reads.

    printf '%s' "$GEMINI_API_KEY" | python3 deploy/encode-key-pool.py
    printf '%s' "$GEMINI_API_KEY" | python3 deploy/encode-key-pool.py --format lines

Reads the raw value on stdin and writes either the canonical JSON array, which
is what Secret Manager stores, or one key per line, which is what the deploy
loops over when it checks each key. Exits non-zero if the value holds no usable
key.

Why this exists
---------------
The agent expects a JSON array, so the value has to be encoded rather than
wrapped in brackets by hand. Hand-wrapping breaks on a key containing a quote,
and double-wraps a value that is already a JSON array -- which is what copying
a key out of another instance gives you. Secret Manager stores either happily;
the break only shows up at runtime, reported as "All N API keys failed", which
reads as a quota problem rather than a bad secret.

So: an existing array passes through unchanged, a comma-separated list becomes
a pool, and json.dumps does the encoding. The result is parsed back before it
is printed, so nothing the agent cannot read can leave here.
"""

import json
import sys


def parse_keys(raw):
    """Recover the keys from a raw value, whatever shape it arrives in."""
    raw = raw.strip()
    try:
        parsed = json.loads(raw)
    except ValueError:
        parsed = None

    if isinstance(parsed, list) and parsed and all(isinstance(k, str) and k for k in parsed):
        return parsed  # already encoded; encoding it again is a no-op
    if isinstance(parsed, str) and parsed:
        return [parsed]
    return [k.strip() for k in raw.split(",") if k.strip()]


def main(argv):
    fmt = "json"
    args = argv[1:]
    if args:
        if len(args) != 2 or args[0] != "--format" or args[1] not in ("json", "lines"):
            print(f"usage: {argv[0]} [--format json|lines]", file=sys.stderr)
            return 2
        fmt = args[1]

    keys = parse_keys(sys.stdin.read())
    if not keys:
        print("GEMINI_API_KEY held no usable key", file=sys.stderr)
        return 1

    if fmt == "lines":
        for key in keys:
            print(key)
        return 0

    encoded = json.dumps(keys)
    # Refuse to hand back something the agent cannot read.
    decoded = json.loads(encoded)
    if not (isinstance(decoded, list) and all(isinstance(k, str) for k in decoded)):
        print("encoded value is not a JSON array of strings", file=sys.stderr)
        return 1
    sys.stdout.write(encoded)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
