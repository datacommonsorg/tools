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

import React, {Component} from 'react';
import * as utils from './utils.js';

const UPLOAD_INSTRUCTIONS = `Upload one MCF file or one set of TMCF+CSV files
to preview in Data Commons. Alternatively, specify a path
to the file in the url, ex: /build/#&file=<path to tmcf>&file=<path to csv>`;

/** Header component contains the id search bar, upload files, and return home
  * button.
  */
class Header extends Component {
  /**
  * Calls utils method goToId to search for an id when the user presses enter.
  * @param {Event} event OnKeyUp  event from html search input element.
  */
  handleSearch(event) {
    if (event.keyCode === 13) {
      utils.searchId(event.target.value);
    }
  }
  /** Renders header element */
  render() {
    return (
      <div className='Header'>
        <div>
          {/* return home button*/}
          <button onClick = {() => utils.goToHome() }>Return Home</button>

          {/* local file selctor*/}
          <input type="file" title={UPLOAD_INSTRUCTIONS} onChange={(event) => {
            this.props.upload(Array.from(event.target.files));
          }}
          accept=".mcf,.tmcf,.csv" required multiple />
        </div>

        {/* search for id w/dropdown of suggestions of the subject nodes*/}
        <input type="search" list="subjIds" onKeyUp={this.handleSearch}
          placeholder="Search by id; default namespace is 'dcid:'"/>
        <datalist id="subjIds">
          {this.props.subjIds.map((subjId) => <option value={subjId}
            key={subjId}/>)}
        </datalist>
      </div>
    );
  }
}
export {Header};
