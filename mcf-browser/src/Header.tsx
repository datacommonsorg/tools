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

const ENTER_KEY = 13;


interface HeaderPropType {
  /**
   * Set a 'search' parameter in url to the specified id.
   */
  searchId: Function;
  /**
   * Return to the home page.
   */
  onHomeClick: React.MouseEventHandler<HTMLButtonElement>;
  /**
   * Ids stored in App's state for the subject nodes of triples from
   * any parsed files.
   */
  subjIds: string[];
}

interface HeaderStateType {
  /**
   * Text input from user via search bar.
   */
  searchVal: string;
}

/** Header component contains the id search bar, upload files, and return home
  * button.
  */
class Header extends Component<HeaderPropType, HeaderStateType> {
  /** Constructor for class, sets initial state
   *
   * @param {Object} props the props passed in by parent component
   */
  constructor(props: HeaderPropType) {
    super(props);
    this.state = {
      searchVal: '',
    };
  }

  /**
  * Calls props method to search for an id when the user presses enter.
  * @param {Event} event OnKeyUp event from html search input element.
  */
  handleSearch(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.keyCode === ENTER_KEY) {
      this.props.searchId(event.target.value);
      this.setState({searchVal: ''});
    }
  }

  /** Renders header element
   * @return {Object} the webpage using JSX code
  */
  render() {
    return (
      <div className='Header'>
        {/* return home button*/}
        <button className='button' onClick={this.props.onHomeClick}>
          Return Home
        </button>

        {/* search for id w/dropdown of suggestions of the subject nodes*/}
        <input type="search" list="subjIds" placeholder="Search by id"
          value={this.state.searchVal}
          onChange={(event) => this.setState({searchVal: event.target.value})}
          onKeyUp={(event) => {
            this.handleSearch(event);
          }}/>
        <datalist id="subjIds">
          {this.props.subjIds.map((subjId) => <option value={subjId}
            key={subjId}/>)}
        </datalist>
      </div>
    );
  }
}

export {Header};
