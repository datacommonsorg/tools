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

test('testing constructor. prov property', () => {
  const fileName = 'fileName.mcf';
  const expectedProv = 'local: fileName';
  const mcfParser = new ParseMcf(fileName);
  expect(mcfParser.prov).toBe(expectedProv);
});

test('testing parsePropValues: should output property values', () => {
  const rawVals = 'val1, l:localNodeId, "GO:BioIdTextVal",schema:remoteNodeId';
  const expectedParsedVals = [
    'val1',
    {'ns' : 'l', 'ref' : 'localNodeId'},
    '"GO:BioIdTextVal"',
    {'ns' : 'schema', 'ref' : 'remoteNodeId'},
  ];
  const fileName = 'fileName';
  const mcfParser = new ParseMcf(fileName);
  mcfParser.lineNum = 0;
  const parsedVals = mcfParser.parsePropValues(rawVals, 0);
  expect(parsedVals).toStrictEqual(expectedParsedVals);

  const expectedErrorMsg = 'Error, no property values to parse (line 0)';
  expect(() => mcfParser.parsePropValues('', 0))
      .toThrow(new Error(expectedErrorMsg));
});

test('testing setCurNode', () => {
  const fileName = 'fileName';
  const mcfParser = new ParseMcf(fileName);

  const noNameSpaceParsedVal = [ 'localNoNameSpaceId' ];
  const noNameSpaceExpectedNode = new Node(noNameSpaceParsedVal[0]);
  mcfParser.setCurNode(noNameSpaceParsedVal);
  expect(mcfParser.curNode).toStrictEqual(noNameSpaceExpectedNode);

  const localNameSpaceParsedVal = [ {'ns' : 'l', 'ref' : 'localNamespaceId'} ];
  const localNameSpaceExpectedNode =
      new Node(localNameSpaceParsedVal[0]['ref']);
  mcfParser.setCurNode(localNameSpaceParsedVal);
  expect(mcfParser.curNode).toStrictEqual(localNameSpaceExpectedNode);

  const remoteNameSpaceParsedVal =
      [ {'ns' : 'ds', 'ref' : 'remoteNamespaceId'} ];

  const remoteNameSpaceExpectedNode =
      new Node(remoteNameSpaceParsedVal[0]['ref']);
  remoteNameSpaceExpectedNode.setDCID(remoteNameSpaceParsedVal[0]['ref']);
  mcfParser.setCurNode(remoteNameSpaceParsedVal);
  expect(mcfParser.curNode).toStrictEqual(remoteNameSpaceExpectedNode);

  const multipleParsedVals = [ 'localId1', 'localId2' ];
  const expectedErrorMsg =
      'Error in declaring node (line -1): localId1,localId2';
  expect(() => mcfParser.setCurNode(multipleParsedVals))
      .toThrow(new Error(expectedErrorMsg));
});

test('testing setCurNodeDCID', () => {
  const fileName = 'fileName.mcf';

  const mcfParser = new ParseMcf(fileName);
  const localId = 'testSrcId';
  const parsedValue = [ '"bio/test"' ];
  mcfParser.curNode = new Node(localId);
  expect(mcfParser.curNode.localId).toBe(localId);
  expect(mcfParser.curNode.dcid).toBe(null);

  mcfParser.setCurNodeDCID(parsedValue);

  expect(mcfParser.curNode.localId).toBe(localId);
  expect(mcfParser.curNode.dcid).toBe('bio/test');

  const errorParsedValues1 = [ '"dcid1"', '"dcid2"' ];
  const expectedErrorMsg1 = 'ERROR setting dcid (line -1): "dcid1","dcid2"';
  expect(() => mcfParser.setCurNodeDCID(errorParsedValues1))
      .toThrow(new Error(expectedErrorMsg1));

  const errorParsedValues2 = [ {'ns' : 'l', 'ref' : '"id"'} ];
  const expectedErrorMsg2 =
      'ERROR setting dcid (line -1): ' + errorParsedValues2;
  expect(() => mcfParser.setCurNodeDCID(errorParsedValues2))
      .toThrow(new Error(expectedErrorMsg2));
});

test('testing string values with createAssertionsFromParsedValues', () => {
  const fileName = 'fileName.mcf';
  const expectedProv = 'local: fileName';

  const mcfParser = new ParseMcf(fileName);
  const localId = 'testId';
  const remoteId = 'remoteSrcId';
  mcfParser.curNode = new Node(localId);
  mcfParser.curNode.setDCID(remoteId);
  const propLabel = 'stringVal';
  const parsedValues = [ 'val1', '"GO:bioTextId"' ];

  mcfParser.createAssertionsFromParsedValues(propLabel, parsedValues);
  const assertions = mcfParser.curNode.getAssertions();

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
  const assertion1 = assertionToJSON(assertions[1]);
  const expectedAssertion = {
    'srcDCID' : remoteId,
    'srclocalId' : localId,
    'property' : propLabel,
    'target' : 'val1',
    'provenance' : expectedProv,
  };
  expect(assertion1).toEqual(expectedAssertion);
  const assertion2 = assertionToJSON(assertions[0]);
  expectedAssertion['target'] = '"GO:bioTextId"';
  expect(assertion2).toEqual(expectedAssertion);
});

test('testing node values with createAssertionsFromParsedValues', () => {
  const fileName = 'fileName.mcf';
  const expectedProv = 'local: fileName';
  const localId = 'localSrcId';
  const mcfParser = new ParseMcf(fileName);
  mcfParser.curNode = new Node(localId);

  const propLabel = 'nodeVal';
  const parsedValues = [
    {'ns' : 'l', 'ref' : 'localId'},
    {'ns' : 'dcs', 'ref' : 'remoteId'},
  ];

  mcfParser.createAssertionsFromParsedValues(propLabel, parsedValues);
  const assertions = mcfParser.curNode.getAssertions();

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
  const assertion1 = assertionToJSON(assertions[1]);
  const expectedAssertion = {
    'srclocalId' : localId,
    'srcDCID' : null,
    'targetlocalId' : 'localId',
    'targetDCID' : null,
    'property' : propLabel,
    'provenance' : expectedProv,
  };
  expect(assertion1).toEqual(expectedAssertion);
  const target1 = assertions[1]['target'];
  expect(target1.invAssertions).toEqual(assertions[1]);

  const assertion2 = assertionToJSON(assertions[0]);
  expectedAssertion['targetDCID'] = 'remoteId';
  expectedAssertion['targetlocalId'] = 'remoteId';
  expect(assertion2).toEqual(expectedAssertion);
  const target2 = assertions[0]['target'];
  expect(target2.invAssertions).toEqual(assertions[0]);
});

test('testing parseLine: ', () => {
  const fileName = 'file_name';
  const mcfParser = new ParseMcf(fileName);

  const testStr1 = '// Node: commentId';
  mcfParser.parseLine(testStr1);
  expect(mcfParser.curNode).toStrictEqual(null);

  const testStr2 = 'Node: localSubjId';
  mcfParser.parseLine(testStr2);
  expect(mcfParser.curNode.localId).toBe('localSubjId');
  expect(mcfParser.curNode.dcid).toBe(null);

  const testStr3 = 'dcid: remoteId';
  mcfParser.parseLine(testStr3);
  expect(mcfParser.curNode.localId).toBe('localSubjId');
  expect(mcfParser.curNode.dcid).toBe('remoteId');

  const testStr4 = ': noPropLabel';
  expect(() => mcfParser.parseLine(testStr4))
      .toThrow(
          new Error('Error, no property label defined (line -1): ' + testStr4));

  const testStr5 = ' : ';
  expect(() => mcfParser.parseLine(testStr5))
      .toThrow(new Error('Error, no property values to parse (line -1)'));
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
  const expectedProv = 'local: fileName';
  const mcfParser = new ParseMcf(fileName);
  const nodeHash = mcfParser.parseMcfStr(mcfStr);

  const obsNode = nodeHash['LocalObsNode'];
  expect(obsNode.localId).toStrictEqual('LocalObsNode');
  expect(obsNode.dcid).toStrictEqual(null);

  const obsAsserts = obsNode.getAssertions();
  expect(obsAsserts.length).toStrictEqual(5);

  for (const assert of obsAsserts) {
    const expectedJSON = {
      'srclocalId' : obsNode.localId,
      'srcDCID' : obsNode.dcid,
      'provenance' : expectedProv,
    };

    const assertJSON = assertionToJSON(assert);
    switch (assert.property) {
    case 'remoteNodeProp':
      expectedJSON['property'] = 'remoteNodeProp';
      expectedJSON['targetlocalId'] = 'StatVarObservation';
      expectedJSON['targetDCID'] = 'StatVarObservation';
      expect(assert.target.invAssertions).toStrictEqual(assert);
      expect(assertJSON).toStrictEqual(expectedJSON);
      break;
    case 'localNodeProp':
      expectedJSON['property'] = 'localNodeProp';

      expectedJSON['targetlocalId'] = 'LocalIndiaNode';
      expectedJSON['targetDCID'] = 'country/IND';
      expect(assert.target.invAssertions).toStrictEqual(assert);
      expect(assertJSON).toStrictEqual(expectedJSON);
      break;

    case 'stringProp':
      expectedJSON['property'] = 'stringProp';

      expectedJSON['target'] = '"2020-08-01"';
      expect(assertJSON).toStrictEqual(expectedJSON);
      break;

    case 'numProp':
      expectedJSON['property'] = 'numProp';

      expectedJSON['target'] = '10000';
      expect(assertJSON).toStrictEqual(expectedJSON);
      break;
    case 'bioID':
      expectedJSON['property'] = 'bioID';
      expectedJSON['target'] = '"GO:bioTextId"';
      expect(assertJSON).toStrictEqual(expectedJSON);
      break;
    default:
      throw new Error('Unexpected assertion: ' + assert);
    }
  }
  expect(obsNode.invAssertions).toStrictEqual(null);

  const indiaNode = nodeHash['LocalIndiaNode'];
  expect(indiaNode.localId).toStrictEqual('LocalIndiaNode');
  expect(indiaNode.dcid).toStrictEqual('country/IND');
  expect(indiaNode.assertions).toStrictEqual(null);

  const indiaInvAsserts = indiaNode.getInvAssertions();

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
    'prov' : expectedProv,
    'target' : indiaNode,
  };
  expect(invAssertJSON).toStrictEqual(expectedInvAssert);
});
