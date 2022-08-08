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

interface FileEntryPropType {
  /**
   * Passes a file list to be submitted to the back-end for parsing.
   */
  upload: Function;
  /**
   * Passes a list of urls to be retrieved, then passed to the back-end for
   * parsing.
   */
  loadFiles: Function;
  /**
   * Return to the home page/reset to current hash stored in App state.
   */
  goToHome: Function;
  /**
   * Sets whether the dropdown on the home page for additonal file entries
   * should be displayed.
   */
  toggle?: Function;
}

interface FileEntryStateType{
  /**
   * Stores user's text entry in the first url entry box. This should be a url
   * to either a MCF or TMCF file.
   */
  mcfTmcfUrl: string;
  /**
   * Stores user's text entry in the second url entry box. This should be a url
   * to a CSV file.
   */
  csvUrl: string;
}

/** Component to display options user has for uploading files. */
class FileEntry extends Component<FileEntryPropType, FileEntryStateType> {
  /** Constructor for class, sets initial state
   * @param {Object} props the props passed in by parent component
   */
  constructor(props: FileEntryPropType) {
    super(props);
    this.state = {
      mcfTmcfUrl: '',
      csvUrl: '',
    };
  }

  /**
   * Submits the urls currently in the text input boxes to be retreived and
   * loaded when the enter key is preessed.
   *
   * @param {Event} event The keyUp event that triggers the function call.
   */
  async handleUrlKeyUp(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.keyCode === 13) {
      if (this.state.mcfTmcfUrl.split('.').pop() === 'mcf') {
        // set the base file hash with the given file names
        await this.props.loadFiles([this.state.mcfTmcfUrl]);
        this.setState({csvUrl: '', mcfTmcfUrl: ''});
        // trigger hash to be set to fileHash
        this.props.goToHome();
        if (this.props.toggle) {
          this.props.toggle();
        }
      } else if (this.state.mcfTmcfUrl.split('.').pop() === 'tmcf' &&
          (this.state.csvUrl.split('.').pop() === 'csv') ) {
        await this.props.loadFiles([this.state.mcfTmcfUrl, this.state.csvUrl]);
        this.setState({csvUrl: '', mcfTmcfUrl: ''});
        // trigger hash to be set to fileHash
        this.props.goToHome();
        if (this.props.toggle) {
          this.props.toggle();
        }
      }
    }
  }

  /**
   * Renders the component by building the JSX.
   *
   * @return {Object} the component using JSX code
   */
  render() {
    return (
      <div className="row" >
        {/* Options to directly upload a file via file selector. */}
        <div className="centered col" >
          <h4>Choose file(s) to upload:</h4>

          {/* upload MCF file(s) */}
          <label className='button'>
            <input type="file" required multiple
              accept=".mcf" onChange={(event) => {
                this.props.upload(Array.from(event.target.files as FileList));
                if (this.props.toggle) {
                  this.props.toggle();
                }
              }}/>
              Upload MCF
          </label>

          {/* upload one pair of TMCF CSV files */}
          <label className='button'>
            <input type="file" required multiple
              accept=".tmcf,.csv" onChange={(event) => {
                this.props.upload(Array.from(event.target.files as FileList));
                if (this.props.toggle) {
                  this.props.toggle();
                }
              }}/>
              Upload TMCF + CSV
          </label>
        </div>

        <div className="centered col">
          <h3>-OR-</h3>
        </div>

        {/* Options to specify url(s) to file(s). */}
        <div className="centered col" >
          <h4>Enter URL(s):</h4>
          <div className="col url-entry" >

            {/* TMCF/MCF url input */}
            <label>MCF / TMCF:
              <input type="text"
                value={this.state.mcfTmcfUrl}
                onChange={(event) =>
                  this.setState({mcfTmcfUrl: event.target.value})}
                onKeyUp={(event) => this.handleUrlKeyUp(event)}/>
            </label>

            {/* CSV url input */}
            <label>CSV:
              <input type="text" placeholder="leave blank for mcf files"
                value={this.state.csvUrl}
                onChange={(event) =>
                  this.setState({csvUrl: event.target.value})}
                onKeyUp={(event) => this.handleUrlKeyUp(event)}/>
            </label>
          </div>
        </div>
      </div>
    );
  }
}


export {FileEntry};
