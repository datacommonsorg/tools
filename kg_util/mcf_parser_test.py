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
"""Tests for mcf_parser."""

# pylint: disable=missing-module-docstring
# pylint: disable=missing-class-docstring
# pylint: disable=missing-function-docstring

import io
import unittest

import mcf_parser


def _triplify(mcf_str):
    return list(mcf_parser.mcf_to_triples(io.StringIO(mcf_str)))


class MCFParserTest(unittest.TestCase):
    def test_failure(self):

        mcf_errmsg_list = [
            ('PropertyWithoutNode: Value',
             'Line 1: Prop-Values before Node or Context block'),
            ('IHaveNoColon',
             'Line 1: Malformed line without a colon delimiter'),
            ("""
              Node: n1
              p1: v1

              Context:
              namespace: rs=http://rs.org
            """, 'Line 5: found Context block after Node'),
            ("""
              Context:
              namespace: foo-http://bar.com
            """, 'Line 3: malformed namespace value'),
            ("""
              Context:
              p1: v1
            """, 'Line 3: Context block only supports "namespace"'),
            ("""
              Context:
              namespace: rs=http://foo.com
              namespace: rs=http://bar.com
            """, 'Line 4: duplicate values for namespace prefix rs:'),
        ]

        for (mcf, errmsg) in mcf_errmsg_list:
            with self.assertRaises(AssertionError) as context:
                _triplify(mcf)
            self.assertTrue(errmsg in str(context.exception))

    def test_success(self):

        mcf_triples_list = [
            (
                # Test simple MCF, with multiple values and different value types.
                """
            Node: MTV
            # City shouldn't be quoted, but we know typeOf is a reference prop.
            typeOf: "City"
            # Mountain View shouldn've been quoted, but we default to value.
            name: Mountain View
            name: "MTV, CA, USA"
            # A local reference to USACountry node.
            containedInPlace: dc/4fef4e, l:USACountry
            population: 81438
            area: 31.788
            inCounty: true
          """,
                [
                    ['MTV', 'typeOf', 'City', 'ID'],
                    ['MTV', 'name', 'Mountain View', 'VALUE'],
                    ['MTV', 'name', 'MTV, CA, USA', 'VALUE'],
                    ['MTV', 'containedInPlace', 'dc/4fef4e', 'ID'],
                    ['MTV', 'containedInPlace', 'l:USACountry', 'ID'],
                    ['MTV', 'population', '81438', 'VALUE'],
                    ['MTV', 'area', '31.788', 'VALUE'],
                    ['MTV', 'inCounty', 'true', 'VALUE'],
                ]),
            (
                # MCF with dcid: notation for node name.
                """
            Node: dcid:dc/mx44
            typeOf: schema:City
            name: "Über"
          """,
                [['dcid:dc/mx44', 'typeOf', 'City', 'ID'],
                 ['dcid:dc/mx44', 'name', 'Über', 'VALUE'],
                 ['dcid:dc/mx44', 'dcid', 'dc/mx44', 'VALUE']]),
            (
                # MCF with Context block.
                """
            Context:
            namespace: "dbc=http://purl.org/dc/terms/"
            namespace: "rs=http://www.openarchives.org/rs/terms/"

            Node: USACountry
            typeOf: Country
            equivalentTo: rs:PaisUSA
            sameAs: dbc:VilleMtv
            name: "United States Of America"
            dcid: "dc/2sffw13"
          """,
                [
                    ['USACountry', 'typeOf', 'Country', 'ID'],
                    [
                        'USACountry', 'equivalentTo',
                        'http://www.openarchives.org/rs/terms/PaisUSA', 'ID'
                    ],
                    [
                        'USACountry', 'sameAs',
                        'http://purl.org/dc/terms/VilleMtv', 'ID'
                    ],
                    [
                        'USACountry', 'name', 'United States Of America',
                        'VALUE'
                    ],
                    ['USACountry', 'dcid', 'dc/2sffw13', 'VALUE'],
                ]),
            (
                # MCF with Complex Value.
                """
            Node: Pop
            typeOf: schema:StatisticalPopulation
            age: [10 20 dcs:Years]
          """,
                [
                    ['Pop', 'typeOf', 'StatisticalPopulation', 'ID'],
                    ['Pop', 'age', '[10 20 dcs:Years]', 'VALUE'],
                ]),
        ]

        for (mcf, want) in mcf_triples_list:
            got = _triplify(mcf)
            self.assertEqual(got, want)


if __name__ == '__main__':
    unittest.main()
