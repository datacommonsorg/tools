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
"""Type aliases for data that is JSON by nature.

`JsonValue` describes any value that `json.loads` can return, and
`JsonObject` describes a decoded JSON object. They type wire payloads whose
shape is open-ended, such as MCP tool arguments and results. Data with a
known shape is parsed into a dedicated type instead. The module uses only the
standard library so that any package in the agent can import it.
"""

type JsonValue = (
    str | int | float | bool | list[JsonValue] | dict[str, JsonValue] | None
)
type JsonObject = dict[str, JsonValue]
