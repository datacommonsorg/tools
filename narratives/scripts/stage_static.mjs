// Copyright 2026 Google LLC
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//      http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

/**
 * Stages the compiled React SPA from ui/dist into the agent/static directory.
 *
 * This mirrors the asset staging performed by narratives/agent/build.sh and
 * narratives/deploy.sh, ensuring that the local Python server and container builds
 * have access to fresh frontend assets.
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const uiDist = path.resolve(__dirname, '../ui/dist');
const staticDir = path.resolve(__dirname, '../agent/static');

const indexHtml = path.join(uiDist, 'index.html');
if (!fs.existsSync(indexHtml)) {
  console.error(
    `FATAL: ${indexHtml} not found — build the UI first with 'pnpm -C ui build'`,
  );
  process.exit(1);
}

fs.rmSync(staticDir, { recursive: true, force: true });
fs.cpSync(uiDist, staticDir, { recursive: true });

function countFiles(dir) {
  let count = 0;
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      count += countFiles(fullPath);
    } else {
      count++;
    }
  }
  return count;
}

const fileCount = countFiles(staticDir);
console.log(`✓ Staged UI build into agent/static (${fileCount} files)`);
