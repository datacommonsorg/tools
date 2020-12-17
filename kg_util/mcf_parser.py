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
"""Library to parse an MCF file into triples."""

# TODO: Support TMCF parsing.
# TODO: Support properties from non-DC/-schema.org namespace.
# TODO: Support complex values enclosed in [] (LatLng, Quantity, QuantityRange).
# TODO: Support provenance and other props in Context block.
# TODO: Add API that returns a map-like structure.

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


def _strip_ns(v):
    return v[v.find(_delim) + 1:]


def _is_schema_ref_property(prop):
    return (prop == 'typeOf' or prop == 'subClassOf' or
            prop == 'subPropertyOf' or prop == 'rangeIncludes' or
            prop == 'domainIncludes' or prop == 'specializationOf')


def _is_common_ref_property(prop):
    return (_is_schema_ref_property(prop) or prop == 'location' or
            prop == 'observedNode' or prop == 'containedInPlace' or
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
    # MCF file line number.
    lno: int = 0
    # Indicates we're within Context block.
    in_context: bool = False
    # Namespace map.
    ns_map: dict = dataclasses.field(default_factory=dict)
    # Current Node block name.
    node: str = ''
    # Indicates whether the current Node block includes dcid property.
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
        return (_strip_ns(value), _ID)
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


def _parse_values(prop, values_str, pc):
    value_pairs = []
    for values in reader([values_str]):
        for value in values:
            value_pairs.append(_parse_value(prop, value.strip(), pc))
        break
    return value_pairs


def _update_ns_map(values_str, pc):
    for values in reader([values_str]):
        for value in values:
            value = _strip_quotes(value.strip())
            parts = value.split('=', 1)
            assert len(parts) == 2, _as_err('malformed namespace value', pc)
            k = parts[0] + _delim
            assert k not in pc.ns_map,\
                _as_err('duplicate values for namespace prefix ' + k, pc)
            pc.ns_map[k] = parts[1].rstrip('/') + '/'
        break


#
# Public Functions
#


def mcf_to_triples(mcf_file):
    """ Parses the file containing a Node MCF graph into triples.

  Args:
    mcf_file: Node MCF file object opened for read.

  Returns:
    An Iterable of triples. Each triple has four values:
      [<subject-id>, <property>, <object-id or object-value>, <'ID' | 'VALUE'>]

  On parse failures, throws AssertionError with a reference to offending line
  number in the MCF file.
  """

    pc = ParseContext()
    for line in mcf_file:
        pc.lno += 1

        line = line.strip()
        if not line or line.startswith('//') or line.startswith('#'):
            continue

        parts = line.split(_delim, 1)
        assert len(parts) == 2,\
            _as_err('Malformed line without a colon delimiter', pc)
        assert parts[0], _as_err('Malformed empty property', pc)
        prop, val_str = parts[0].strip(), parts[1].strip()

        if prop == _context:
            # New Context block.
            assert not pc.node, _as_err('found Context block after Node', pc)
            pc.in_context = True

        elif prop == _node:
            # New Node block.
            assert val_str, _as_err('Node with no name', pc)
            assert ',' not in val_str, _as_err('Malformed Node name with ","',
                                               pc)
            assert not val_str.startswith('"'),\
                _as_err('Malformed Node name starting with "', pc)

            # Finalize current node.
            if (pc.node and not pc.has_dcid and _is_global_ref(pc.node)):
                yield [pc.node, _dcid, _strip_ns(pc.node), _VALUE]

            # Update to new node.
            pc.node = val_str
            pc.in_context = False
            pc.has_dcid = False

        elif pc.in_context:
            # Processing inside Context block.
            assert prop == _namespace,\
                _as_err('Context block only supports "namespace" property', pc)
            _update_ns_map(val_str, pc)

        else:
            # Processing inside Node block.
            assert pc.node, _as_err('Prop-Values before Node or Context block',
                                    pc)

            for vp in _parse_values(prop, val_str, pc):
                yield [pc.node, prop, vp[0], vp[1]]

            if prop == _dcid:
                pc.has_dcid = True

    # Finalize current node.
    if (pc.node and not pc.has_dcid and _is_global_ref(pc.node)):
        yield [pc.node, _dcid, _strip_ns(pc.node), _VALUE]


if __name__ == '__main__':
    with open(sys.argv[1], 'r') as f:
        for t in mcf_to_triples(f):
            print(t)
