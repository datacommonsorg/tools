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
 * @fileoverview Debug panel section listing the places a turn's observation
 * calls referenced.
 */

import { formatPlacesHeading } from '@/src/components/panel_debug/copy_debug';
import {
  DEBUG_MONO_TEXT_CLASSES,
  DebugSection,
} from '@/src/components/panel_debug/section_debug';

interface PlacesSectionProps {
  /** Place DCIDs, deduplicated. */
  places: string[];
}

/** Lists the place DCIDs under a counted heading; renders nothing without places. */
export const PlacesSection = ({ places }: PlacesSectionProps) => {
  if (places.length === 0) {
    return null;
  }
  return (
    <DebugSection label={formatPlacesHeading(places.length)}>
      <p className={`m-0 ${DEBUG_MONO_TEXT_CLASSES} wrap-anywhere`}>
        {places.join(', ')}
      </p>
    </DebugSection>
  );
};
