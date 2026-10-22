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
"""Provenance and source attribution records for observation tables and digests.

Defines `Source` for dataset citations so that every layer represents source
attribution as a hashable, immutable domain value.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Source:
    """One data source cited by an observation table or script result.

    Attributes:
        name: Display name of the dataset or publishing organization.
        url: Provenance URL for the source.
        license: License identifier or name when reported by metadata.
        provider: Publishing organization name when distinct from a handle.
        dataset: Dataset name (`isPartOf`) when reported by metadata.
        date_range: Year coverage string (for example `"1960 - 2023"`).
    """

    name: str
    url: str
    license: str | None = None
    provider: str | None = None
    dataset: str | None = None
    date_range: str | None = None
