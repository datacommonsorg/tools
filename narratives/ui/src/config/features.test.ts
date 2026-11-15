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
 * @fileoverview Tests the shipped build-time feature flags.
 */

import { expect, it } from 'vitest';
import { IS_PDF_EXPORT_ENABLED } from '@/src/config/features';

it('ships with PDF export disabled', () => {
  // Test: The shipped PDF export setting.
  // Situation: The flag as built, with no mock.
  // Expectation: PDF export is off.
  expect(IS_PDF_EXPORT_ENABLED).toBe(false);
});
