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

import {ParsingError} from './back-end/utils';

interface ParsingErrorsTablePropType {
  /**
  * The App state's parsingErrs list of error message Objects from parsing
  * files. Each object in the array contains one file name and one list of
  * errors found in that file.
  */
 errsList: ParsingError[];
}

/* Simple component to render the parsing errors table. */
const ParsingErrorsTable = (props: ParsingErrorsTablePropType) => {
  if (!props.errsList.length) {
    return null;
  }
  return (
    <div className = 'box'>
      <h3>Parsing Errors</h3>
      <table>
        <thead><tr>
          <th>File Name</th>
          <th>Line Num</th>
          <th>Line</th>
          <th>Error Message</th>
        </tr></thead>
        <tbody>
          {props.errsList.map((errObj) => (
            errObj['errs'].map((msg) =>
              <tr key={msg[0]}>
                <td>{errObj['file']}</td>
                <td>{msg[0]}</td>
                <td>{msg[1]}</td>
                <td>{msg[2]}</td>
              </tr>,
            )))}
        </tbody>
      </table>
    </div>
  );
};

export {ParsingErrorsTable};
