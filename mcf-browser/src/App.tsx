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

import axios from 'axios';
import React, {Component} from 'react';

import {Series} from './back-end/data';
import {Node} from './back-end/graph';
import * as API from './back-end/server-api';
import {ParsingError} from './back-end/utils';
import {DisplayNode} from './DisplayNode';
import {Header} from './Header';
import {Home} from './Home';
import * as utils from './utils';

/** Interface for the App component's state */
interface AppStateType {
  /**
   * Subject node IDs of the triples from files uploaded by user.
   */
  subjNodes: string[];
  /**
   * Node that should be displayed.
   */
  curNode: Node | null;
  /**
   * Files that have been uploaded by user.The locality of the csv files in
   * relation to the tmcf files is very important! The csv will be paired with
   * the closest tmcf file that comes before it whenever we are loading/parsing
   * the files in the backend.
   */
  files: Blob[];
  /**
   * Indicates if any files are currently being parsed by back-end.
   */
  loading: boolean;
  /**
   * Indicates if url needs to be parsed on component mount. True when the
   * application first loads and when files are cleared by user.
   */
  firstLoad: boolean;
  /**
   * Array of error message objects, one object per parsed file with errors. The
   * property 'errs' is in each object is an array of String arrays, one String
   * array per error within the given file which specifies line number, line,
   * and helpful message indicating the error. The 'file' property provides the
   * file name from which the error came.
   */
  parsingErrs: ParsingError[];
  /**
   * Contains the remote files specified by user in url format to be used as a
   * home base in the hash portion of the url while using those files.
   */
  fileHash: string;
  /**
   * Time series data uploaded by the user
   */
  timeData: Series[];
}

/** Drives the entire app and holds the state of the files and current node. */
class App extends Component<{}, AppStateType> {
  initialState: Readonly<AppStateType>;
  /** Constructor for class, sets initial state
   *
   * @param {Object} props the props passed in by parent component
   */
  constructor(props: Object) {
    super(props);
    this.state = {
      subjNodes: [],
      curNode: null,
      files: [],
      loading: false,
      firstLoad: true,
      parsingErrs: [],
      fileHash: '#',
      timeData: [],
    };
    // save state for easy reset when user 'clears' files
    this.initialState = this.state;
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
      node = API.retrieveNode(nodeId, /* shouldCreateRemote */ false);
    } else {
      nodeId = params.get('search');
      if (nodeId) {
        node = API.retrieveNode(nodeId, /* shouldCreateRemote */ true);
      }
    }
    this.setState({curNode: node});
  }

  /**
   * Parses the URL upon the first load of the app. It loads the files that
   * are specfied or navigates to a node if an id specified by the search
   * param.
   */
  parseUrl() {
    const params = new URLSearchParams(window.location.hash.trim());
    const fileUrls = params.getAll('file');

    if (fileUrls.length) {
      this.loadRemoteFiles(fileUrls);
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
   * Saves the file params as part of App's state so that the files remain in
   * the hash of the url when navigating between nodes.
   * @param {Array<String>} fileUrlList File url list to be saved in the hash.
   */
  appendfileHash(fileUrlList: string[]) {
    let hash = this.state.fileHash;
    for (const fileUrl of fileUrlList) {
      hash += '&file=' + fileUrl;
    }
    this.setState({fileHash: hash});
  }

  /**
   * Retrieves file Blobs from array of file Urls, submits the new blobs to be
   * parsed, and appends them to App's state list of files uploaded by user.
   * @param {Array<string>} fileUrls The array of file urls to load and append
   *     to App state's files object.
   */
  async loadRemoteFiles(fileUrls: string[]) {
    this.appendfileHash(fileUrls);

    const newFiles = [];
    for (const fileUrl of fileUrls) {
      const res = await axios.request({
        url: fileUrl,
        method: 'GET',
        responseType: 'blob', // important
      });

      res.data.name = fileUrl;
      newFiles.push(res.data);

      this.setState((prevState) => ({
        files: [...prevState.files, res.data],
      }));
    }
    this.submitFileList(newFiles);
  }

  /**
   * Saves the list of new blob files to App' state list of files and submits
   * them to be parsed.
   * @param {Array<Blob>} fileList File blobs selcted by user via file picker.
   */
  async uploadFiles(fileList: Blob[]) {
    for (const file of fileList) {
      await this.setState((prevState) => ({
        files: [...prevState.files, file],
      }));
    }
    this.submitFileList(this.state.files);
  }

  /**
   * Passes list of file blobs to the 'back-end' API to be parsed and loaded
   * into memory.
   * @param {Array<Blob>} fileList File blobs to be parsed by back-end.
   */
  submitFileList(fileList: Blob[]) {
    this.setState({loading: true});

    API.readFileList(fileList).then((res) => {
      this.setState(() => ({
        parsingErrs: res['errMsgs'],
        subjNodes: res['localNodes'],
        loading: false,
      }), () => this.handleHashChange());
    });
  }

  /**
   * Clear App state and calls the 'back-end' API clearFiles method.
   */
  onClearPress() {
    this.setState(this.initialState);
    API.clearFiles();
    utils.goTo('');
  }

  /**
   * Renders the browser by displaying a specific node or the homepage.
   *
   * @return {Object} the webpage using TSX code
   */
  render() {
    return (
      <div id="app">
        <Header
          subjIds={this.state.subjNodes}
          onHomeClick={() => utils.goTo(this.state.fileHash)}
          searchId={(id: string) => utils.searchId(this.state.fileHash, id)}
        />

        {this.state.curNode ? (
          // if curNode is set, then display it
          <DisplayNode
            node={this.state.curNode}
            goToId={(id: string) => utils.goToId(this.state.fileHash, id)}
          />
        ) : (
          // otherwise display home
          <Home
            fileList={this.state.files}
            clear={() => this.onClearPress()}
            errs={this.state.parsingErrs}
            loading={this.state.loading}
            subjNodes={this.state.subjNodes}
            upload={(files: Blob[]) => this.uploadFiles(files)}
            goToId={(id: string) => utils.goToId(this.state.fileHash, id)}
            loadFiles={(filesList: string[]) => this.loadRemoteFiles(filesList)}
            goToHome={() => utils.goTo(this.state.fileHash)}
            timeData={this.state.timeData}
          />
        )}
      </div>
    );
  }
}

export {App};
