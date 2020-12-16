# Copyright 2020 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Library functions to parse an MCF file into other forms."""

# TODO: Add API that returns a map-like structure
# TODO: Support TMCF parsing
# TODO: Support properties from non-DC/-schema.org namespace
# TODO: Support complex values enclosed in [] (LatLng, Quantity, QuantityRange)

from csv import reader
import dataclasses
import sys


_VALUE = 'VALUE'
_ID = 'ID'
_node = 'Node'
_context = 'Context'
_dcid = 'dcid'
_namespace = 'namespace'
_dcid_prefix = 'dcid:'
_dcs_prefix = 'dcs:'
_schema_prefix = 'schema:'
_local_prefix = 'l:'
_delim = ':'


#
# Internal Functions
#

def _strip_quotes(s):
  if s.startswith('"') and s.endswith('"'):
    return s[1:-1]
  return s


def _is_schema_ref_property(prop):
  return (prop == 'typeOf' or prop == 'subClassOf' or
          prop == 'subPropertyOf' or prop == 'rangeIncludes' or
          prop == 'domainIncludes' or prop == 'specializationOf')


def _is_common_ref_property(prop):
  return (_is_schema_ref_property(prop) or prop == 'location' or
          prop== 'observedNode' or prop == 'containedInPlace' or
          prop == 'containedIn' or prop == 'populationType' or
          prop == 'measuredProperty' or prop == 'measurementDenominator' or
          prop == 'populationGroup' or prop == 'constraintProperties' or
          prop == 'measurementMethod' or prop == 'comparedNode')


def _is_global_ref(value):
  return (value.startswith(_dcid_prefix) or value.startswith(_dcs_prefix) or
          value.startswith(_schema_prefix))


def _is_local_ref(value):
  return value.startswith(_local_prefix)


@dataclasses.dataclass
class ParseContext:
  """Context used for parser"""
  lno: int = 0
  current_node: str = ''
  in_context: bool = False
  ns_map: dict = dataclasses.field(default_factory=dict)
  has_dcid: bool = False


def _as_err(msg, pc):
  return 'Line ' + str(pc.lno) + ': ' + msg


def _parse_value(prop, value, pc):
  expect_ref = _is_common_ref_property(prop)

  if value.startswith('"'):
    assert len(value) > 2 and value.endswith('"'),\
        _as_err('malformed string', pc)
    value = _strip_quotes(value)
    if not expect_ref:
      return (value, _VALUE)

  if _is_global_ref(value):
    return (value[value.find(_delim) + 1:], _ID)
  elif _is_local_ref(value):
    # For local ref, we retain the prefix.
    return (value, _ID)
  else:
    ns_prefix = value.split(':', 1)[0] + _delim
    if ns_prefix != value and ns_prefix in pc.ns_map:
      value = value.replace(ns_prefix, pc.ns_map[ns_prefix], 1)
      return (value, _ID)

  if expect_ref:
    # If we're here, user likely forgot to add a "dcid:", "dcs:" or "schema:"
    # prefix.  We cannot tell apart if they failed to add an local ref ('l:'),
    # but we err on the side of user being careful about adding local refs and
    # accept the MCF without failing.
    return (value, _ID)

  return (value, _VALUE)


def _parse_line(line, pc):
  line = line.strip()
  if not line or line.startswith('//') or line.startswith('#'):
    return '', []
  prop, rest = line.split(_delim, 1)
  value_pairs = []
  for values in reader([rest]):
    for value in values:
      if pc.in_context and prop == _namespace:
        value = _strip_quotes(value.strip())
        parts = value.split('=', 1)
        assert len(parts) == 2, _as_err('malformed namespace value', pc)
        pc.ns_map[parts[0] + _delim] = parts[1].rstrip('/') + '/'
      else:
        value_pairs.append(_parse_value(prop, value.strip(), pc))
    break
  return prop, value_pairs


#
# Public functions
#

def mcf_to_triples(mcf_file):
  """ Parses the file containing a Node MCF graph into triples.

  Args:
    mcf_file: Input Node MCF file.

  Returns:
    An Iterable of triples. Each triple has four values:
      [<subject-id>, <property>, <object-id or object-value>, <'ID' | 'VALUE'>]

  On parse failures, throws AssertionError with a reference to offending line
  number in the MCF file.
  """

  pc = ParseContext()
  with open(mcf_file, 'r') as f:
    for line in f:
      pc.lno += 1
      prop, value_pairs = _parse_line(line, pc)
      if not prop:
        continue
      if prop == _node:
        assert len(value_pairs) == 1, _as_err('Node with no name', pc)
        assert value_pairs[0], _as_err('Node has multiple values', pc)
        if (pc.current_node and not pc.has_dcid and
            _is_global_ref(pc.current_node)):
          yield [pc.current_node, _dcid, _strip_ns(pc.current_node), _VALUE]
        pc.in_context = False
        pc.current_node = value_pairs[0][0]
        pc.has_dcid = False
      elif prop == _context:
        assert not pc.current_node, _as_err('found Context after Node', pc)
        pc.in_context = True
      else:
        if pc.in_context:
          continue
        assert pc.current_node, _as_err('prop/values without Node block', pc)
        for vp in value_pairs:
          yield [pc.current_node, prop, vp[0], vp[1]]
        if prop == _dcid:
          pc.has_dcid = True


if __name__ == '__main__':
  for t in mcf_to_triples(sys.argv[1]):
    print(t)
