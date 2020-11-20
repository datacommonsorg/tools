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
import {LoadingSpinner, openFile, goToId} from './utils.js';

/* Simple component to render the parsing errors table. */
const ParsingErrorsTable = (props) => {
  if (!props.errsList.length) {
    return null;
  }
  return (
    <div >
      <h3 className="underline">Parsing Errors</h3>
      <table>
        <thead><tr>
          <th>Line Num</th>
          <th>Line</th>
          <th>Error Message</th>
        </tr></thead>
        <tbody>
          {props.errsList.map((msg) => (
            <tr key={msg[0]}>
              <td>{msg[0]}</td>
              <td>{msg[1]}</td>
              <td>{msg[2]}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

/** Displays the currently loaded files, clear button, parsing errors, and
  * subject nodes.
  */
class Home extends Component {
  render() {
    return (
      <div className="centered col">

        <h3>Current Files:</h3>
        {/* list current file names*/}
        <ul>
          {this.props.fileList.map((file) => {
            const className = file.name.startsWith('https:') ? 'clickable' : '';

            return (<li className={className} key={file.name} onClick={() => {
              if (className) openFile(file.name);
            }}>{file.name}</li>);
          })}
        </ul>
        <br/>

        {/* display clear files button*/}
        <button onClick={this.props.clear} >Clear</button>
        <br/>
        {/* display parsing errors, if any*/}
        <ParsingErrorsTable errsList={this.props.errs}/>

        <h3>Subject Nodes:</h3>
        {/* display loading animation while waiting*/}
        <LoadingSpinner loading={this.props.loading}
          msg='...loading mcf...'/>

        {/* display list of subject noode ids*/}
        <ul>
          {this.props.subjNodes.map((dcid) =>
            <li className='clickable' key={dcid} onClick={() =>
              goToId(dcid)}>{dcid}</li>)}
        </ul>
      </div>
    );
  }
}

export {Home};
