/**
 * Copyright 2022 Google LLC
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

import {LoadingSpinner} from './LoadingSpinner';

interface GraphExplorerPropType {
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

/** Component to display the Graph explorer */
class GraphExplorer extends Component<GraphExplorerPropType> {
  /** Constructor for class, sets initial state
   * @param {Object} props the props passed in by parent component
   */
  constructor(props: GraphExplorerPropType) {
    super(props);
    this.state = {};
  }

  /** Renders the GraphExplorer component.
   * @return {Object} the component using TSX code
   */
  render() {
    return (
      <div className="box">
        {/* display loading animation while waiting*/}
        <LoadingSpinner loading={this.props.loading} msg="...loading mcf..." />

        {/* display list of subject node ids*/}
        <h3>Subject Nodes</h3>
        <ul>
          {this.props.subjNodes.map((dcid) => (
            <li
              className="clickable"
              key={dcid}
              onClick={() => this.props.goToId(dcid)}
            >
              {dcid}
            </li>
          ))}
        </ul>
      </div>
    );
  }
}

export {GraphExplorer};
