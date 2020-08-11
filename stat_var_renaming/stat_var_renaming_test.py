# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
  This file contains various tests for methods used in the Statiistical variable renaming.

    TODO(iancostello): Finish test coverage.
"""

import stat_var_renaming as svr
import stat_var_renaming_constants as svrc
import stat_var_renaming_functions as svrf
import unittest

def test_with_remap(test_cases, function):
    remapper = svrf.remap_numerical_quantities({})

    for prop, constraint, expected in test_cases:
        if remapper[prop][0](prop, constraint) != expected:
            return False

    return True

class TestHelperMethods(unittest.TestCase):
    def test_standard_name_remapper(self):
        self.assertEqual(svrf.standard_name_remapper("Some,list,Of,stuff"), 'SomeListOfStuff')
        self.assertEqual(svrf.standard_name_remapper("Google small-query"), 'GoogleSmallQuery')
        self.assertEqual(svrf.standard_name_remapper("Bells and Whistles"), 'BellsWhistles')

class TestPropertyRemappers(unittest.TestCase):
    def test_regex_remapping(self):
        test_cases = [
            ('householderAge', 'Years25To44', '25To44Years'),
            ('income', 'USDollar100000To124999', '100000To124999USDollar'),
            ('age', 'Years15Onwards', '15OrMoreYears'),
            ('age', 'YearsUpto1', 'Upto1Years'),
            ('detailedLevelOfSchool', 'EnrolledInGrade1', 'EnrolledInGrade1')
        ]

        self.assertTrue(test_with_remap(test_cases, svrf.remap_numerical_quantities))

    def test_naics_remapping(self):
        test_cases = [
            ('naics', 'Years25To44', '25To44Years'),
            ('income', 'USDollar100000To124999', '100000To124999USDollar'),
            ('age', 'Years15Onwards', '15OrMoreYears'),
            ('age', 'YearsUpto1', 'Upto1Years'),
            ('detailedLevelOfSchool', 'EnrolledInGrade1', 'EnrolledInGrade1')
        ]




if __name__ == '__main__':
    unittest.main()