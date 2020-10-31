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

import {Node} from '../graph.js';
import {ParseMcf} from '../parse-mcf.js';
import {ERROR_MESSAGES} from '../utils.js';

test('testing constructor. prov property', () => {
  const fileName = 'fileName.mcf';
  const mcfParser = new ParseMcf(fileName);
  expect(mcfParser.prov).toBe(fileName);
});

test('testing parsePropValues: should output property values', () => {
  const rawVals = 'val1, l:localNodeId, "GO:BioIdTextVal",schema:remoteNodeId,'+
    ' "A, B", "B, C,D"';
  const expectedParsedVals = [
    'val1',
    {'ns' : 'l', 'ref' : 'localNodeId'},
    'GO:BioIdTextVal',
    {'ns' : 'schema', 'ref' : 'remoteNodeId'},
    'A, B',
    'B, C,D',
  ];
  const fileName = 'fileName';
  const mcfParser = new ParseMcf(fileName);
  mcfParser.lineNum = 0;
  const parsedVals = mcfParser.parsePropValues(rawVals, 0);
  expect(parsedVals).toStrictEqual(expectedParsedVals);

});

test('testing setCurNode', () => {
  const fileName = 'fileName';
  const mcfParser = new ParseMcf(fileName);

  const noNameSpaceParsedVal = [ 'localNoNameSpaceId' ];
  const noNameSpaceExpectedNode = new Node('l:' + noNameSpaceParsedVal[0]);
  mcfParser.setCurNode(noNameSpaceParsedVal);
  expect(mcfParser.curNode).toStrictEqual(noNameSpaceExpectedNode);

  const remoteNameSpaceParsedVal =
      [ {'ns' : 'dcid', 'ref' : 'remoteNamespaceId'} ];

  const remoteNameSpaceExpectedNode =
      new Node('l:dcid:'+remoteNameSpaceParsedVal[0]['ref']);
  remoteNameSpaceExpectedNode.setDCID(remoteNameSpaceParsedVal[0]['ref']);
  mcfParser.setCurNode(remoteNameSpaceParsedVal);
  expect(mcfParser.curNode).toStrictEqual(remoteNameSpaceExpectedNode);
});

test('testing setCurNodeDCID', () => {
  const fileName = 'fileName.mcf';

  const mcfParser = new ParseMcf(fileName);
  const localId = 'l:testSrcId';
  const parsedValue = [ 'bio/test' ];
  mcfParser.curNode = new Node(localId);
  expect(mcfParser.curNode.localId).toBe(localId);
  expect(mcfParser.curNode.dcid).toBe(null);

  mcfParser.setCurNodeDCID(parsedValue);

  expect(mcfParser.curNode.localId).toBe(localId);
  expect(mcfParser.curNode.dcid).toBe('bio/test');

});

test('testing string values with createAssertionsFromParsedValues', () => {
  const fileName = 'fileName.mcf';

  const mcfParser = new ParseMcf(fileName);
  const localId = 'l:testId';
  const remoteId = 'remoteSrcId';
  mcfParser.curNode = new Node(localId);
  mcfParser.curNode.setDCID(remoteId);
  const propLabel = 'stringVal';
  const parsedValues = [ 'val1', '"GO:bioTextId"' ];

  mcfParser.createAssertionsFromParsedValues(propLabel, parsedValues);
  const assertions = mcfParser.curNode.assertions;

  const assertionToJSON = (assertion) => {
    const {property, target, provenance} = assertion;
    return {
      'srclocalId' : assertion.src.localId,
      'srcDCID' : assertion.src.dcid,
      property,
      target,
      provenance,
    };
  };

  // note assertions are returned backwards due to nature of linked list
  const assertion1 = assertionToJSON(assertions[0]);
  const expectedAssertion = {
    'srcDCID' : remoteId,
    'srclocalId' : localId,
    'property' : propLabel,
    'target' : 'val1',
    'provenance' : fileName,
  };
  expect(assertion1).toEqual(expectedAssertion);
  const assertion2 = assertionToJSON(assertions[1]);
  expectedAssertion['target'] = '"GO:bioTextId"';
  expect(assertion2).toEqual(expectedAssertion);
});

test('testing node values with createAssertionsFromParsedValues', () => {
  const fileName = 'fileName.mcf';
  const localId = 'l:localSrcId';
  const mcfParser = new ParseMcf(fileName);
  mcfParser.curNode = new Node(localId);

  const propLabel = 'nodeVal';
  const parsedValues = [
    {'ns' : 'l', 'ref' : 'localId'},
    {'ns' : 'dcs', 'ref' : 'remoteId'},
  ];

  mcfParser.createAssertionsFromParsedValues(propLabel, parsedValues);
  const assertions = mcfParser.curNode.assertions;

  const assertionToJSON = (assertion) => {
    const {property, provenance} = assertion;
    return {
      'srclocalId' : assertion.src.localId,
      'srcDCID' : assertion.src.dcid,
      'targetlocalId' : assertion.target.localId,
      'targetDCID' : assertion.target.dcid,
      property,
      provenance,
    };
  };

  // note assertions are returned backwards due to nature of linked list
  const assertion1 = assertionToJSON(assertions[0]);
  const expectedAssertion = {
    'srclocalId' : localId,
    'srcDCID' : null,
    'targetlocalId' : 'l:localId',
    'targetDCID' : null,
    'property' : propLabel,
    'provenance' : fileName,
  };
  expect(assertion1).toEqual(expectedAssertion);
  const target1 = assertions[0]['target'];
  expect(target1.invAssertions[0]).toEqual(assertions[0]);

  const assertion2 = assertionToJSON(assertions[1]);
  expectedAssertion['targetDCID'] = 'remoteId';
  expectedAssertion['targetlocalId'] = null;
  expect(assertion2).toEqual(expectedAssertion);
  const target2 = assertions[1]['target'];
  expect(target2.invAssertions[0]).toEqual(assertions[1]);
});

test('testing parseLine: ', () => {
  const fileName = 'file_name';
  const mcfParser = new ParseMcf(fileName);

  const testStr1 = '// Node: commentId';
  mcfParser.parseLine(testStr1);
  expect(mcfParser.curNode).toStrictEqual(null);

  const testStr2 = 'Node: localSubjId';
  mcfParser.parseLine(testStr2);
  expect(mcfParser.curNode.localId).toBe('l:localSubjId');
  expect(mcfParser.curNode.dcid).toBe(null);

  const testStr3 = 'dcid: remoteId';
  mcfParser.parseLine(testStr3);
  expect(mcfParser.curNode.localId).toBe('l:localSubjId');
  expect(mcfParser.curNode.dcid).toBe('remoteId');


});

const mcfStr = `
Node: LocalObsNode
remoteNodeProp: dcs:StatVarObservation
localNodeProp: l:LocalIndiaNode
stringProp: "2020-08-01"
numProp: 10000
// comment
bioID: "GO:bioTextId"

Node: LocalIndiaNode
dcid: "country/IND"
`;
// TODO finish test
test('testing ParseMcfStr: ', () => {
  const assertionToJSON = (assertion) => {
    const {property, provenance} = assertion;
    const json = {
      'srclocalId' : assertion.src.localId,
      'srcDCID' : assertion.src.dcid,
      property,
      provenance,
    };
    if (assertion.target instanceof Node) {
      json['targetlocalId'] = assertion.target.localId;
      json['targetDCID'] = assertion.target.dcid;
    } else {
      json['target'] = assertion.target;
    }
    return json;
  };

  // e2e test, from mcf string to nodes/assertions
  const fileName = 'fileName.mcf';
  const mcfParser = new ParseMcf(fileName);
  const errs = mcfParser.parseMcfStr(mcfStr);

  const obsNode = ParseMcf.localNodeHash['l:LocalObsNode'];
  expect(obsNode.localId).toStrictEqual('l:LocalObsNode');
  expect(obsNode.dcid).toStrictEqual(null);

  const obsAsserts = obsNode.assertions;
  expect(obsAsserts.length).toStrictEqual(5);

  for (const assert of obsAsserts) {
    const expectedJSON = {
      'srclocalId' : obsNode.localId,
      'srcDCID' : obsNode.dcid,
      'provenance' : fileName,
    };

    const assertJSON = assertionToJSON(assert);
    switch (assert.property) {
    case 'remoteNodeProp':
      expectedJSON['property'] = 'remoteNodeProp';
      expectedJSON['targetlocalId'] = null;
      expectedJSON['targetDCID'] = 'StatVarObservation';
      expect(assert.target.invAssertions[0]).toStrictEqual(assert);
      expect(assertJSON).toStrictEqual(expectedJSON);
      break;
    case 'localNodeProp':
      expectedJSON['property'] = 'localNodeProp';

      expectedJSON['targetlocalId'] = 'l:LocalIndiaNode';
      expectedJSON['targetDCID'] = 'country/IND';
      expect(assert.target.invAssertions[0]).toStrictEqual(assert);
      expect(assertJSON).toStrictEqual(expectedJSON);
      break;

    case 'stringProp':
      expectedJSON['property'] = 'stringProp';

      expectedJSON['target'] = '2020-08-01';
      expect(assertJSON).toStrictEqual(expectedJSON);
      break;

    case 'numProp':
      expectedJSON['property'] = 'numProp';

      expectedJSON['target'] = '10000';
      expect(assertJSON).toStrictEqual(expectedJSON);
      break;
    case 'bioID':
      expectedJSON['property'] = 'bioID';
      expectedJSON['target'] = 'GO:bioTextId';
      expect(assertJSON).toStrictEqual(expectedJSON);
      break;
    default:
      throw new Error('Unexpected assertion: ' + assert);
    }
  }
  expect(obsNode.invAssertions).toStrictEqual([]);

  const indiaNode = ParseMcf.localNodeHash['l:LocalIndiaNode'];
  expect(indiaNode.localId).toStrictEqual('l:LocalIndiaNode');
  expect(indiaNode.dcid).toStrictEqual('country/IND');
  expect(indiaNode.assertions).toStrictEqual([]);

  const indiaInvAsserts = indiaNode.invAssertions;

  expect(indiaInvAsserts.length).toStrictEqual(1);

  const invAssertJSON = {
    'src' : indiaInvAsserts[0].src,
    'prop' : indiaInvAsserts[0].property,
    'prov' : indiaInvAsserts[0].provenance,
    'target' : indiaInvAsserts[0].target,
  };
  const expectedInvAssert = {
    'src' : obsNode,
    'prop' : 'localNodeProp',
    'prov' : fileName,
    'target' : indiaNode,
  };
  expect(invAssertJSON).toStrictEqual(expectedInvAssert);
});

test('testing errors: ', () => {
  const fileName = 'fileName.mcf';
  const mcfParser = new ParseMcf(fileName);

  mcfParser.setCurNode([ 'localId1', 'localId2' ]); // #1
  mcfParser.setCurNode([{'ns':'invalid', 'ref':  'localId1'}]) // #2
  mcfParser.createAssertionsFromParsedValues(['val']) // #3

  mcfParser.setCurNode([ 'localId1' ]);
  mcfParser.setCurNodeDCID(['dcid1', 'dcid2']) // #4
  mcfParser.setCurNodeDCID([{'ns':'dcid', 'ref':'remote'}]) // #5

  mcfParser.setCurNodeDCID(['dcid1'])
  mcfParser.setCurNodeDCID(['dcid2']) // #6

  mcfParser.parseLine('prop') // #7
  mcfParser.parseLine(':val') // #8
  mcfParser.parseLine('val:') // #9

  expect(mcfParser.errors).toEqual([
    [-1, undefined, ERROR_MESSAGES['curNode-length']], // #1
    [-1, undefined, ERROR_MESSAGES['curNode-ns']], // #2
    [-1, undefined, ERROR_MESSAGES['assert-noCur']], // #3
    [-1, undefined, ERROR_MESSAGES['setDCID-multiple']], // #4
    [-1, undefined, ERROR_MESSAGES['setDCID-ref']], // #5
    [-1, undefined, ERROR_MESSAGES['setDCID']], // #6
    [-1, undefined, ERROR_MESSAGES['parse-noColon']], // #7
    [-1, undefined, ERROR_MESSAGES['parse-noLabel']], // #8
    [-1, undefined, ERROR_MESSAGES['parse-noValues']], // #9
   ]);

});
