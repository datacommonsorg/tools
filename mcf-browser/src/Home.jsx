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
import {openFile} from './utils.js';
import {LoadingSpinner} from './LoadingSpinner.jsx';
import {ParsingErrorsTable} from './ParsingErrorsTable.jsx';
import {FileEntry} from './FileEntry.jsx';

interface HomePropType {
  /**
   * List of the files that have been uploaded by user.
   */
  fileList: Blob[];
  /**
   * Passes a file list to be submitted to the back-end for parsing.
   */
  upload: func;
  /**
   * Passes a list of urls to be retrieved, then passed to the back-end for parsing.
   */
  loadFiles: func;
  /**
   * Return to the home page.
   */
  goToHome: func;
  /**
   * Clears the loaded data from all files and resets App to its initial state.
   */
  clear: func;
  /**
   * Error messages from parsing files specifying line number, line, and helpful
   * message indicating the error.
   */
  errs: string[][];
  /**
   * Indicates if uploaded files are currently being parsed.
   */
  loading: boolean;
  /**
   * Nodes stored in App's state which are the subject nodes of triples from
   * any parsed files.
   */
  subjNodes: Node[];
  /**
   * Set id parameter in url to the given id. Used when user clicks a subject node to explore.
   */
  goToId: func;
}

interface HomeStateType{
  /**
   * Determines if the file entry dropdown option should be displayed.
   */
  dropdown: boolean;
 }

/** Displays the currently loaded files, clear button, parsing errors, and
  * subject nodes.
  */
class Home extends Component {
  constructor(props) {
    super(props);
    this.state = {
      dropdown: false,
    };
  }

  toggleDropdown() {
    this.setState({dropdown: !this.state.dropdown});
  }

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

    if(this.state.dropdown){
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

export {Home};
