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
import {TriplesTable} from './TriplesTable.js';
import {LoadingSpinner} from './utils.js';

/* Simple component to render the colors legend. */
const ColorLegend = () => {
  return (
    <div>
      <p className = 'inline'> | </p>
      <p className='inline' id='blue'>Node has dcid that exists in DC KG</p>
      <p className = 'inline'> | </p>
      <p className='inline' id='purple'>Node has resolved local reference and
        no dcid</p>
      <p className = 'inline'> | </p>
      <p className='inline' id='orange'>Node has unresolved local reference and
        no dcid</p>
      <p className = 'inline'> | </p>
      <p className='inline' id='red'>Default; Node has dcid which does not exist
        in DC KG</p>
      <p className = 'inline'> | </p>
    </div>
  );
};

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
    console.log(this.props.node);

    const curNode = this.props.node;
    this.setState({
      ref: curNode.getRef(),
      fetching: true,
      asserts: [],
      invAsserts: [],
    });

    API.getElemId(curNode).then((elemId) => this.setState({elemId: elemId}));

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
        <ColorLegend />
        <br/>
        <h1 className='inline'>Currently Viewing: </h1>
        <h1 className='inline' id={this.state.elemId}>{this.state.ref}</h1>
        <br/>
        <LoadingSpinner loading={this.state.fetching}
          msg='...fetching triples...'/>
        <br/>
        <h3 className='inline padded'>Node Properties</h3>
        <p className='inline'> - current node is source</p>
        <br/>
        <TriplesTable triples={this.state.asserts} inverse={false}/>
        <br/>
        <h3 className='inline padded'>Incoming Properties from Other Nodes</h3>
        <p className='inline'> - current node is target</p>
        <br/>
        <TriplesTable triples={this.state.invAsserts} inverse={true}/>
      </div>
    );
  }
}
export {DisplayNode};
