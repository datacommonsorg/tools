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
import {PageBar} from './PageBar';

const NODES_PER_PAGE = 25;

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

interface GraphExplorerStateType {
  /** Tracks which page the user is currently viewing (0-indexed) */
  page: number;
}

/** Component to display the Graph explorer */
class GraphExplorer extends Component<
  GraphExplorerPropType,
  GraphExplorerStateType
> {
  /** Constructor for class, sets initial state
   * @param {Object} props the props passed in by parent component
   */
  constructor(props: GraphExplorerPropType) {
    super(props);
    this.state = {
      page: 0,
    };
  }

  /** Renders the GraphExplorer component.
   * @return {Object} the component using TSX code
   */
  render() {
    const maxPage = Math.ceil(this.props.subjNodes.length / NODES_PER_PAGE);
    const switchPage = (page: number) => this.setState({page});
    return (
      <div className="box">
        {/* display loading animation while waiting*/}
        <LoadingSpinner loading={this.props.loading} msg="...loading mcf..." />

        {/* display list of subject node ids*/}
        <h3>Graph Explorer</h3>
        <ul>
          {this.props.subjNodes.slice(
              this.state.page * NODES_PER_PAGE,
              (this.state.page + 1) * NODES_PER_PAGE,
          ).map((dcid) => (
            <li
              className="clickable"
              key={dcid}
              onClick={() => this.props.goToId(dcid)}
            >
              {dcid}
            </li>
          ))}
        </ul>
        <PageBar
          page={this.state.page}
          maxPage={maxPage}
          goToNextPage={
            (currPage: number, maxPage: number) => {
              switchPage(PageBar.getNextPage(currPage, maxPage));
            }
          }
          goToPrevPage={
            (currPage: number) => {
              switchPage(PageBar.getPrevPage(currPage));
            }
          }
          goToPage={
            (newPage: number) => {
              switchPage(newPage - 1);
            }
          }
        />
      </div>
    );
  }
}

export {GraphExplorer};
