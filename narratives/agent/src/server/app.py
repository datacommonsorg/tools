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
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os

from flask import Flask
from flask_cors import CORS

# Configuration
PROXY_PORT = int(os.environ.get("PROXY_PORT", 5001))

# Flask app
app = Flask(__name__)
# Scoped CORS. ALLOWED_ORIGIN defaults to "*" so dev still works
# without configuration; production sets this to the Cloud Run service URL
# (comma-separated for multiple origins).
CORS(app, origins=os.environ.get("ALLOWED_ORIGIN", "*").split(","))
