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
import PropTypes from 'prop-types';

import {Node} from './back-end/graph.js';
import {openFile} from './utils.js';
import {LoadingSpinner} from './LoadingSpinner.jsx';
import {ParsingErrorsTable} from './ParsingErrorsTable.jsx';
import {FileEntry} from './FileEntry.jsx';

/** Displays the currently loaded files, clear button, parsing errors, and
  * subject nodes.
  */
class Home extends Component {
  /** Constructor for class, sets initial state
   *
   * @param {Object} props the props passed in by parent component
   */
  constructor(props) {
    super(props);
    this.state = {
      dropdown: false,
    };
  }

  /**
   * Toggles the boolean value of this.state.dropdown
   * whenever user expands or collapses the dropdown
   */
  toggleDropdown() {
    this.setState({dropdown: !this.state.dropdown});
  }

  /**
   * Renders the component
   *
   * @return {Object} the webpage using JSX code
   */
  render() {
    if (this.props.fileList.length === 0) {
      // show file entry options, but do not toggle dropdown on file submission
      return (
        <div className="home centered col">
          <div className="box ">
            <FileEntry upload={this.props.upload}
              loadFiles={this.props.loadFiles}
              goToHome={this.props.goToHome}
              toggle={() => {}}/>
          </div>
        </div>
      );
    }

    let addFileButtonClass;
    let addFileButtonText;

    if (this.state.dropdown) {
      addFileButtonClass = 'button expanded';
      addFileButtonText = 'Add File (-)';
    } else {
      addFileButtonClass = 'button';
      addFileButtonText = 'Add File (+)';
    }

    // show current files and subject nodes
    return (
      <div className="centered col">

        {/* list current file names*/}
        <div className = "box">
          <h3>Current Files</h3>
          <ul>
            {this.props.fileList.map((file, index) => {
              const className = file.name.startsWith('https:') ?
                'clickable' : '';
              return (
                <li onClick={() => {
                  if (className) openFile(file.name);
                }}
                className={className} key={file.name+index}>{file.name}</li>
              );
            })}
          </ul>
          <br/>

          {/* display clear files button*/}
          <button className='button' onClick={this.props.clear} >Clear</button>

          <button className={addFileButtonClass} onClick={() =>
            this.toggleDropdown()}>{addFileButtonText}</button>

          {this.state.dropdown ?
            <FileEntry
              upload={this.props.upload}
              loadFiles={this.props.loadFiles}
              goToHome={this.props.goToHome}
              toggle={() => this.toggleDropdown()}/> : null }

        </div>
        <br/>

        {/* display parsing errors, if any*/}
        <ParsingErrorsTable errsList={this.props.errs}/>
        <br/>

        <div className = "box">

          {/* display loading animation while waiting*/}
          <LoadingSpinner loading={this.props.loading}
            msg='...loading mcf...'/>

          {/* display list of subject noode ids*/}
          <h3>Subject Nodes</h3>
          <ul>
            {this.props.subjNodes.map((dcid) =>
              <li className='clickable' key={dcid}
                onClick={() => this.props.goToId(dcid)}>{dcid}</li>)}
          </ul>
        </div>

      </div>
    );
  }
}

Home.propTypes = {
  fileList: PropTypes.arrayOf(PropTypes.instanceOf(Blob)),
  upload: PropTypes.func,
  loadFiles: PropTypes.func,
  goToHome: PropTypes.func,
  clear: PropTypes.func,
  errs: PropTypes.arrayOf(PropTypes.arrayOf(PropTypes.string)),
  loading: PropTypes.bool,
  subjNodes: PropTypes.arrayOf(PropTypes.instanceOf(Node)),
  goToId: PropTypes.func,
};

export {Home};
