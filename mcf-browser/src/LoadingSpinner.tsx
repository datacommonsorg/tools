/**
 * Copyright 2020 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

import React from 'react';


interface LoadingSpinnerPropType {
  /**
   * Indicates if spinner should be displayed.
   */
  loading: boolean;
  /**
   * The message to be displayed while page is loading
   */
  msg: string;
}


interface LoadingSpinnerPropType {
  /**
   * Indicates if spinner should be displayed.
   */
  loading: boolean;
  /**
   * The message to be displayed while page is loading
   */
  msg: string;
}

// spinning animation to demonstrate loading, used in DisplayNode and Home
const LoadingSpinner = (props: LoadingSpinnerPropType) => {
  if (!props.loading) {
    return null;
  }
  return (
    <div className='centered col'>
      <br/>
      <div className='loadingSpinner'></div>
      <h2>{props.msg}</h2>
    </div>
  );
};

export {LoadingSpinner};
