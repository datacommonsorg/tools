/**
 Copyright 2020 Google LLC

 Licensed under the Apache License, Version 2.0 (the "License");
 you may not use this file except in compliance with the License.
 You may obtain a copy of the License at

 https://www.apache.org/licenses/LICENSE-2.0

 Unless required by applicable law or agreed to in writing, software
 distributed under the License is distributed on an "AS IS" BASIS,
 WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 See the License for the specific language governing permissions and
 limitations under the License.
 */

import MultiButtonGroup from './MultiButtonGroup';
import React from 'react';

type TableIndexPaginationPropsType = {
  index: number;
  totalIndexCount: number;
  onIndexChange: (index: number) => void;
};

/**
 * Component that displays pagination buttons below the Table.
 * @param props.index: active page.
 * @param props.totalIndexCount: total amount of pages.
 * @param props.onIndexChange: what should happen when the user changes page.
 */
export default (props: TableIndexPaginationPropsType) => {
  const MAX_THRESHOLD = 5; // The maximum amount of buttons to display.
  const totalIndexCount = props.totalIndexCount; // How many pages are there?

  // Create an array from 0 to totalIndexCount.
  let indexArray = Array.from(Array(totalIndexCount).keys());

  // If there are more pages than our MAX_THRESHOLD.
  // Slice the array and push the last number in the array.
  // We don't wanna show 100 buttons.
  // Example: [0, 1, 2, 3, 4, 100]
  if (props.totalIndexCount > MAX_THRESHOLD) {
    indexArray = indexArray.slice(0, MAX_THRESHOLD);
    indexArray.push(props.totalIndexCount - 1);
  }

  // For every index in the array, create a button.
  // When clicked, the button will change the index + 1.
  const numberButtons = indexArray.map(index => {
    return {
      active: props.index === index,
      text: String(index + 1),
      onClick: () => props.onIndexChange(index),
    };
  });

  // Previous button object.
  const prevButton = {
    active: props.index !== 0,
    text: 'Previous',
    onClick: () => props.onIndexChange(props.index - 1),
  };

  // Next button object.
  const nextButton = {
    active: props.index !== props.totalIndexCount,
    text: 'Next',
    onClick: () => props.onIndexChange(props.index + 1),
  };

  const allButtons = [prevButton, ...numberButtons, nextButton];

  return <MultiButtonGroup items={allButtons} />;
};
