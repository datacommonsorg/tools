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
"""Golden fixtures for the analytics library.

`core_golden.json` holds the serialized output of the analytics functions
over a fixed set of inputs. `regenerate_golden.py` rebuilds it, and
`golden_test.py` fails when the current code no longer reproduces it, so
every change to a figure is a deliberate, reviewed diff.
"""
