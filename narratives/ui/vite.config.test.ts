/**
 * Copyright 2026 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
 * implied. See the License for the specific language governing
 * permissions and limitations under the License.
 */

/**
 * @fileoverview Tests that `vite.config.ts` keeps `/` in development and emits
 * relative `./assets/...` URLs in production HTML builds.
 */

import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { build, type Rollup } from 'vite';
import { afterEach, describe, expect, it } from 'vitest';
import viteConfig from '@/vite.config';

const tempDirs: string[] = [];

afterEach(() => {
  for (const dir of tempDirs.splice(0)) {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

describe('vite.config', () => {
  it('uses "/" as base during local development', () => {
    // Test: Base path configured for `vite dev`.
    // Situation: `viteConfig` is evaluated with `command: "serve"`.
    // Expectation: `base` is `"/"` so `/agent` dev-proxy routes stay at root.
    const config = viteConfig({ command: 'serve', mode: 'development' });
    expect(config.base).toBe('/');
  });

  it('emits relative ./assets/ and public asset paths in production index.html', async () => {
    // Test: Relative asset URL rewriting during `vite build`.
    // Situation: `vite build` runs with the `base` configured by `vite.config.ts`
    //            against an `index.html` referencing `/dc-logo.svg` and an ES
    //            module entry script.
    // Expectation: The compiled `index.html` rewrites both the favicon and the
    //              hashed bundle script to `./`-prefixed relative paths so the
    //              bundle loads under any runtime `BASE_PATH` subpath.
    const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'narratives-vite-'));
    tempDirs.push(tempDir);
    fs.mkdirSync(path.join(tempDir, 'public'));
    fs.writeFileSync(path.join(tempDir, 'public', 'dc-logo.svg'), '<svg/>');
    fs.writeFileSync(path.join(tempDir, 'entry.ts'), 'export const ready = 1;');
    fs.writeFileSync(
      path.join(tempDir, 'index.html'),
      [
        '<!doctype html>',
        '<link rel="icon" href="/dc-logo.svg" />',
        '<script type="module" src="/entry.ts"></script>',
      ].join('\n'),
    );

    const prodConfig = viteConfig({ command: 'build', mode: 'production' });
    expect(prodConfig.base).toBe('./');

    const result = (await build({
      configFile: false,
      root: tempDir,
      base: prodConfig.base,
      logLevel: 'silent',
      build: { write: false },
    })) as Rollup.RollupOutput;

    const htmlAsset = result.output.find(
      (item): item is Rollup.OutputAsset =>
        item.type === 'asset' && item.fileName === 'index.html',
    );
    expect(htmlAsset).toBeDefined();
    const html = String(htmlAsset?.source ?? '');
    expect(html).toContain('href="./dc-logo.svg"');
    expect(html).toMatch(/src="\.\/assets\/index-[^"]+\.js"/);
    expect(html).not.toContain('src="/assets/');
  });
});
