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
"""Rejects adversarial queries with regex rules before any model call.

Normalizes the query (`normalize_query`) and matches it against patterns
grouped by attack family (`PREFILTER_PATTERNS`); `prefilter_match` returns the
first family matched so the classify phase can refuse the turn without
spending a classifier call.
"""

import re
import unicodedata

# Zero-width spaces, joiners, byte-order marks, and soft hyphens stripped prior
# to pre-filter matching.
_INVISIBLE_CHARS = re.compile("[\u200b\u200c\u200d\u2060\ufeff\u00ad]")

# Compiled regex patterns paired with the attack family logged on a match.
# Instruction-override rules require an explicit instruction noun paired with
# `all`, `any`, `your`, or `system` so conversational self-corrections
# ("ignore the previous prompt, I meant Texas") and analytical constraints
# ("ignore the previous constraints on years") pass through to the classifier.
PREFILTER_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (family, re.compile(pattern, re.IGNORECASE))
    for family, pattern in (
        (
            "instruction_override",
            r"\b(ignore|disregard|forget)\s+"
            r"((all|any|your)\s+(of\s+)?(the\s+)?"
            r"(previous|prior|above|earlier|preceding)\s+"
            r"(system\s+)?(instructions?|prompts?|directives?)|"
            r"(the\s+)?(previous|prior|above|earlier|preceding)\s+"
            r"system\s+(instructions?|prompts?|directives?))\b",
        ),
        (
            "persona_override",
            r"\byou\s+are\s+now\s+(acting\s+as\s+)?(an?\s+)?"
            r"(unrestricted|unfiltered|unmoderated)\b",
        ),
        (
            "persona_override",
            r"\bpretend\s+(you\s+are|to\s+be|you're)\s+(an?\s+)?"
            r"(unmoderated|unrestricted|unfiltered)\b",
        ),
        (
            "secret_exfiltration",
            r"\b(reveal|print|output|dump|show|display|repeat|leak|"
            r"exfiltrate)\b[^.?!]{0,40}?"
            r"\b(system|initial|original|hidden)\s*(prompt|instructions)\b",
        ),
        (
            "secret_exfiltration",
            r"\b(GEMINI_API_KEY(_SECRET)?|DC_API_KEY|TRANSCRIPT_HMAC_SECRET)"
            r"\b|\.env\.local\b",
        ),
        (
            "jailbreak_mode",
            r"\b(DAN\s+mode|developer\s+mode|god\s+mode|system\s+override|"
            r"new\s+system\s+directive)\b",
        ),
        (
            "injection_payload",
            r";\s*DROP\s+TABLE\b"
            r"|\bUNION\s+(ALL\s+)?SELECT\s+(NULL\b|\*|[^.?!]*"
            r"\b(information_schema|sqlite_master|pg_catalog|password)\b)"
            r"|'\s*OR\s+'?1'?\s*=\s*'?1"
            r"|\$\{jndi:ldap://"
            r"|/etc/passwd\b"
            r"|169\.254\.169\.254"
            r"|metadata\.google\.internal",
        ),
    )
)


def normalize_query(text: str) -> str:
    """Normalizes `text` for pre-filter pattern matching.

    Applies NFKC compatibility decomposition, strips invisible formatting
    characters, and collapses whitespace runs to a single space.
    """
    folded = unicodedata.normalize("NFKC", text)
    return " ".join(_INVISIBLE_CHARS.sub("", folded).split())


def prefilter_match(query: str) -> str | None:
    """Returns the first pre-filter family matched by `query`, or `None`."""
    normalized = normalize_query(query)
    for family, pattern in PREFILTER_PATTERNS:
        if pattern.search(normalized):
            return family
    return None
