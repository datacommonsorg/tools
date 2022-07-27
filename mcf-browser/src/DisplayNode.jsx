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

import * as API from './back-end/server-api.js';
import {TriplesTable} from './TriplesTable.jsx';
import {LoadingSpinner} from './LoadingSpinner.jsx';
import {colorLegend} from './utils.js';

interface DisplayNodePropType {
  /**
   * Node object to be displayed to user
   */
  node: Node;
  /**
   * Set id parameter in url to the given id.
   */
  goToId: func;
}

interface DisplayNodeStateType {
  /**
   * The reference of the node to be displayed to the user.
   * ex: 'country/IND [l:LocalIndiaNode]'.
   */
  ref: string;
  /**
   * Indicates if triples are currently being fetched from the Data Commons
   * Knowledge Graph.
   */
  fetching: boolean;
  /**
   * The triples that the current node is the subject (or source) of.
   */
  asserts: Assertion[];
  /**
   * The triples that the current node is the target of.
   */
  invAsserts: Assertion[];
  /**
   * The class of the element containing the reference of the node should be.
   */
  elemClass: string;
 }

/** Displays node data for a given node passed in through props. */
class DisplayNode extends Component {
  /** Creates DisplayNode component. */
  constructor(props) {
    super(props);
    this.state = {
      ref: null,
      asserts: [],
      invAsserts: [],
      fetching: true,
    };
  }

  /** Sets node data when the component mounts. */
  componentDidMount() {
    this.setNodeData();
  }

  /**
   * Sets node data when the node to display changes.
   * @param {Object} prevProps The previous props before the component updated,
   *     used to compare if the passed in node has changed.
   */
  componentDidUpdate(prevProps) {
    if (prevProps.node !== this.props.node) {
      this.setNodeData();
    }
  }

  /**
   * Loads data to display for the node passed in through props. This includes
   * fetching the remote data from DC KG for the node.
   */
  setNodeData() {
    const curNode = this.props.node;
    this.setState({
      ref: curNode.getRef(),
      fetching: true,
      asserts: [],
      invAsserts: [],
      elemClass: '',
    });

    API.getElemClass(curNode).then((elemClass) => {
      this.setState({elemClass: elemClass});
    });

    curNode.fetchRemoteData().then(() => {
      this.setState({
        asserts: curNode.assertions,
        invAsserts: curNode.invAssertions,
        fetching: false,
      });
    });
  }

  /** Renders the DisplayNode component. */
  render() {
    return (
      <div>
        <br/>
        <h1 className='inline'>Currently Viewing: </h1>
        <span title={colorLegend[this.state.elemClass]}>
          <h1 className={'inline ' + this.state.elemClass}>{this.state.ref}</h1>
        </span>
        <br/>
        <LoadingSpinner loading={this.state.fetching}
          msg='...fetching triples...'/>
        <br/>
        <h3 className='inline padded'>Node Properties</h3>
        <p className='inline'> - current node is source</p>
        <br/>
        <TriplesTable triples={this.state.asserts} inverse={false}
          goToId={this.props.goToId}/>
        <br/>
        <h3 className='inline padded'>Incoming Properties from Other Nodes</h3>
        <p className='inline'> - current node is target</p>
        <br/>
        <TriplesTable triples={this.state.invAsserts} inverse={true}
          goToId={this.props.goToId}/>
      </div>
    );
  }
}
export {DisplayNode};
