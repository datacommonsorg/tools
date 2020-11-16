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

import './index.css';

import React, {Component} from 'react';

import {DisplayNode} from './DisplayNode.js';
import {Header} from './Header.js';
import {Home} from './Home.js';
import * as utils from './utils.js';
import * as API from './back-end/server-api.js';


/* Drives the entire app and holds the state of the files and current node. */
class App extends Component {
  constructor(props) {
    super(props);
    this.state = {
      subjNodes: [],
      curNode: null,
      fileList: [],
      loading: false,
      firstLoad: true,
      parsingErrs: [],
    };
  }

  /**
   * Adds an event listener to the window to respond to url hash changes. Calls
   * the method to parse the url if the mount is the first time loading the app.
   */
  componentDidMount() {
    window.addEventListener('hashchange', () => this.handleHashChange(), false);
    if (this.state.firstLoad) {
      this.parseUrl();
      this.setState({firstLoad: false});
    }
  }

  /**
    * Parses the URL upon the first load of the app. It loads the files that
    * are specfied or navigates to a node if an id specified by the search
    * param.
    */
  parseUrl() {
    const params = new URLSearchParams(window.location.hash.split('#')[1]);
    const fileUrls = params.getAll('file');

    if (fileUrls.length) {
      this.loadRemoteFiles(0, fileUrls);
      utils.setFileHash(fileUrls);
    } else {
      // get node to display from url
      const searchId = params.get('search');
      if (searchId) {
        const node = API.retrieveNode(searchId, /* shouldCreateRemote */ true);
        this.setState({curNode: node});
      }
    }
  }

  /**
  * Sets App state according to url parameters 'id' and 'search'.
  * The param 'id' is only set when the user clicks to the next node while
  * navigating the triples tables or the subject nodes list.
  * The 'search' param is set when the user uses the search bar. This causes
  * the dcid of the retreived node to try to be set so that a node will always
  * be displayed when a user seearches for it. If it does not exist in the KG,
  * then the node id will appear red in the display.
  */
  handleHashChange() {
    let node = null;

    const params = new URLSearchParams(window.location.hash.split('#')[1]);
    let nodeId = params.get('id');

    if (nodeId) {
      node = API.retrieveNode(nodeId, /* shouldCreateRemote*/ false);
    } else {
      nodeId = params.get('search');
      if (nodeId) {
        node = API.retrieveNode(nodeId, /* shouldCreateRemote*/ true);
      }
    }
    this.setState({curNode: node});
  }

  /**
  * Gets a remote file from an Array of urls at index i and appends the
  * retrieved file to App state's fileList. This is a recursive method that
  * calls itself to iterate through the entire Array of fileUrls.
  * @param {number} i The index of the url to get from fileUrls array.
  * @param {Array<string>} fileUrls The array of file urls to load and append
  *     to App state's fileList.
  */
  loadRemoteFiles(i, fileUrls) {
    if (i >= fileUrls.length) {
      this.submitFileList();
      return;
    }

    const xhr = new XMLHttpRequest();
    xhr.responseType = 'blob';
    xhr.open('GET', fileUrls[i]);

    xhr.onload = () => {
      xhr.response.name = fileUrls[i];
      this.setState({
        fileList: this.state.fileList.concat(xhr.response),
      }, () => this.loadRemoteFiles(i + 1, fileUrls));
    };

    xhr.send();
  }

  /**
  * Passes App state's fileList array to the 'back-end' API to be parsed and
  * the files loaded into memory.
  */
  submitFileList() {
    this.setState({loading: true});

    API.readFileList(this.state.fileList).then((res) => {
      this.setState({
        parsingErrs: res['errMsgs'],
        subjNodes: res['localNodes'],
        loading: false,
      }, () => this.handleHashChange());
    });
  }

  /**
    * Clear App state and calls the 'back-end' API clearFiles method.
    */
  onClearPress() {
    this.setState({
      subjNodes: [],
      fileList: [],
      loading: false,
      parsingErrs: [],
    });
    API.clearFiles();
    utils.setFileHash('');
    window.location.hash = '';
  }

  /**
    * Save and submit files uploaded from 'Choose File' selector in the Header.
    */
  uploadFiles(filesList) {
    this.setState({
      curNode: null,
      fileList: this.state.fileList.concat(filesList),
    }, () => this.submitFileList());
  }

  /**
    * Renders the browser by displaying a specific node or the homepage.
    */
  render() {
    return (
      <div>
        <Header upload={(files) => this.uploadFiles(files)}
          subjIds={this.state.subjNodes}/>

        {this.state.curNode ?
            // if curNode is set, then display it
            <DisplayNode node={this.state.curNode} /> :
            // otherwise display home
            <Home fileList={this.state.fileList}
              clear={() => this.onClearPress()}
              errs={this.state.parsingErrs}
              loading={this.state.loading}
              subjNodes={this.state.subjNodes}/>
        }
      </div>
    );
  }
}
export {App};
