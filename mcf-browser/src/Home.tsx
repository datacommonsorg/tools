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

import {ParsingError} from './back-end/utils';
import {openFile} from './utils';
import {ParsingErrorsTable} from './ParsingErrorsTable';
import {FileEntry} from './FileEntry';
import {GraphExplorer} from './GraphExplorer';


interface HomePropType {
  /**
   * List of the files that have been uploaded by user.
   */
  fileList: Blob[];
  /**
   * Passes a file list to be submitted to the back-end for parsing.
   */
  upload: Function;
  /**
   * Passes a list of urls to be retrieved, then passed to the back-end
   * for parsing.
   */
  loadFiles: Function;
  /**
   * Return to the home page.
   */
  goToHome: Function;
  /**
   * Clears the loaded data from all files and resets App to its initial state.
   */
  clear: React.MouseEventHandler<HTMLButtonElement>;
  /**
   * Error messages from parsing files specifying line number, line, and helpful
   * message indicating the error.
   */
  errs: ParsingError[];
  /**
   * Indicates if uploaded files are currently being parsed.
   */
  loading: boolean;
  /**
   * IDs for nodes stored in App's state which are the subject nodes of
   * triples from any parsed files.
   */
  subjNodes: string[];
  /**
   * Set id parameter in url to the given id. Used when user clicks a
   * subject node to explore.
   */
  goToId: Function;
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
class Home extends Component<HomePropType, HomeStateType> {
  /** Constructor for class, sets initial state
   *
   * @param {Object} props the props passed in by parent component
   */
  constructor(props: HomePropType) {
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
            />
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
              const fileName = (file as File).name;
              const className = fileName.startsWith('https:') ?
                'clickable' : '';
              return (
                <li onClick={() => {
                  if (className) openFile(fileName);
                }}
                className={className} key={fileName+index}>{fileName}</li>
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

        <GraphExplorer
          loading={this.props.loading}
          subjNodes={this.props.subjNodes}
          goToId={this.props.goToId}
        />

      </div>
    );
  }
}

export {Home};
