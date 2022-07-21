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
import PropTypes from 'prop-types';

import Assertion from './back-end/graph.js';
import * as API from './back-end/server-api.js';
import * as utils from './utils.js';

const NON_BREAKING_SPACE = '\u00a0';

/** Displays all given assertions as a table of triples. */
export class TriplesTable extends Component {
  /** Constructor for class, sets initial state
   *
   * @param {Object} props the props passed in by parent component
   */
  constructor(props) {
    super(props);

    this.state = {
      tableRows: null,
      loading: true,
    };
  }

  /**
  * Gets rows of triples when the array of Assertions from props is updated.
  * @param {Object} prevProps The previous props before the component
  *     updated, used to compare if the passed in triples have been modified.
  */
  componentDidUpdate(prevProps) {
    if (prevProps.triples !== this.props.triples) {
      this.setState({loading: true});
      this.getTripleRows().then((rows) => {
        this.setState({
          tableRows: rows,
          loading: false,
        });
      });
    }
  }
  /**
  * Returns an html element containing the styled source if the triple is
  * inverse and the styled target otherwise.
  * @param {Node|string} target The source of an inverse assertion or the target
  *     of a direct assertion.
  * @return {HtmlElement} A single cell of an html row representing a triple.
  *     Either the source or target of the triple depending if the triple is
  *     inverse or not.
  */
  async getTargetCell(target) {
    if (API.isNodeObj(target)) {
      const elemClass = await API.getElemClass(target);
      return (
        <div>
          <span title={utils.colorLegend[elemClass]}>
            <p className ={'clickable ' + elemClass} onClick ={() =>
              this.props.goToId(target.localId || target.dcid)}>
              {target.getRef()}
            </p>
          </span>
        </div>
      );
    }
    return (<p>{target}</p>);
  }

  /**
  * Returns an html element containing the styled provenance of the triple. The
  * provenance if of one of the following formats:
  *     dc/<dcid>
  *     <local mcf file>
  *     <local tmcf file>&<local csv file>
  *     https://<mcf file path>
  *     https://<tmcf path>&https://<csv path>
  *
  * @param {string} prov The provenance of the triple.
  * @return {HtmlElement} A single cell of an html row representing a triple.
  *     Either the source or target of the triple depending if the triple is
  *     inverse or not.
  */
  getProvenanceCell(prov) {
    if (prov.startsWith('dc/')) {
      // data commons provenance id
      return (<p className='clickable dc-provenance'onClick={() =>
        this.props.goToId(prov)}>{prov}</p>);
    }

    if (!prov.startsWith('https')) {
      // local file(s) as provenance
      return (<p>{prov.replace('&', ', ')}</p>);
    }

    if (!prov.includes('&')) {
      // single mcf file as provenance
      return (<p className='clickable' onClick={() =>
        utils.openFile(prov)}>{prov.split('/').pop()}</p>);
    }

    // provenance is one tmcf and one csv

    const fileNames = [];
    const provNames = [];
    for (const fileName of prov.split('&')) {
      fileNames.push(fileName);
      provNames.push(fileName.split('/').pop());
    }

    return (
      <div>
        <p className='clickable' onClick={() =>
          utils.openFile(fileNames[0])}>{provNames[0]}</p>
        <p>,{NON_BREAKING_SPACE}</p>
        <p className='clickable' onClick={() =>
          utils.openFile(fileNames[1])}>{provNames[1]}</p>
      </div>
    );
  }

  /**
  * Converts a list of Assertion objects to an array of HTML row elements that
  * is displyed in the TriplesTable.
  *
  * @return {Array<HtmlElement>} The array of HTML row elements representing
  *     each triple.
  */
  async getTripleRows() {
    const tripleRows = [];
    let index = 0; // used to create a unique key for each row element

    for (const assert of this.props.triples) {
      const missingVal = this.props.inverse ? assert.src : assert.target;
      const val = await this.getTargetCell(missingVal);

      const prov = this.getProvenanceCell(assert.provenance);

      let rowClassName;
      if (!assert.provenance.startsWith('dc/')) {
        // triple is not from DC KG, therefore the row should be bold
        rowClassName = 'bold';
      }

      tripleRows.push(
          <tr className={rowClassName} key={index}>
            <td>{assert.property}</td>
            <td>{val}</td>
            <td>{prov}</td>
          </tr>,
      );
      index += 1;
    }
    return tripleRows;
  }

  /** Renders TriplesTable component.
   * @return {Object} component using JSX code
   */
  render() {
    if (this.state.loading) {
      // return null when loading to prevent error in rendering Promise objects
      return null;
    }
    const tableHeaders = this.props.inverse ? (
        <tr>
          <th>Property</th>
          <th>Source</th>
          <th>Provenance</th>
        </tr>
      ) : (
      <tr>
        <th>Property</th>
        <th>Target</th>
        <th>Provenance</th>
      </tr>
    );

    return (
      <table>
        <thead>
          {tableHeaders}
        </thead>
        <tbody>
          {this.state.tableRows}
        </tbody>
      </table>
    );
  }
}

TriplesTable.propTypes = {
  triples: PropTypes.arrayOf(PropTypes.instanceOf(Assertion)),
  inverse: PropTypes.bool,
  goToId: PropTypes.func,
};
