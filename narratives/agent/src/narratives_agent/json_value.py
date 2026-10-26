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
"""Type aliases and conversion for data that is JSON by nature.

`JsonValue` describes any value that `json.loads` can return, and
`JsonObject` describes a decoded JSON object. They type wire payloads whose
shape is open-ended, such as MCP tool arguments and results. Data with a
known shape is parsed into a dedicated type instead. `json_safe` converts
typed values, such as dataclasses, back into a `JsonValue`. The module uses
only the standard library so that any package in the agent can import it.
"""

import dataclasses
import math
from collections.abc import Mapping

type JsonValue = (
    str | int | float | bool | list[JsonValue] | dict[str, JsonValue] | None
)
type JsonObject = dict[str, JsonValue]


def json_safe(value: object) -> JsonValue:
    """Recursively converts `value` into plain JSON-serializable Python types.

    Converts dataclasses to dicts, tuples and sets to lists, and non-finite
    floats (`NaN`, `Infinity`, `-Infinity`) to `None` so that strict JSON
    encoders (`json.dumps(..., allow_nan=False)`) never reject the output.

    Raises:
        TypeError: If `value` or any nested element cannot be represented in
            JSON.
    """
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: json_safe(getattr(value, field.name))
            for field in dataclasses.fields(value)
        }
    if isinstance(value, Mapping):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [json_safe(item) for item in value]
    if isinstance(value, set | frozenset):
        return sorted((json_safe(item) for item in value), key=str)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, str) or value is None:
        return value
    raise TypeError(
        f"Cannot serialize value of type {type(value).__name__} to JSON."
    )
