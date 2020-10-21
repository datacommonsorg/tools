# Copyright 2020 Google LLC
#
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

import unittest
from calculate_data import _pct_changes


class TestPctChanges(unittest.TestCase):
    def test_one_day_from_baseline(self):
        """
        Simple 1-day percent increase with valid ints.
        """
        data = {'2020-01-02': 10,
                '2020-01-03': 20,
                '2020-01-04': 40}

        actual = _pct_changes(list(data.items()), days_from_baseline=1)
        expected = {'2020-01-03': 100,
                    '2020-01-04': 100}

        self.assertListEqual(actual, list(expected.items()))

    def test_zero_and_negative_values(self):
        """
        Tests to make sure that negative values are accepted
        and zero divisions are omitted.
        """
        data = {'2020-01-02': -10,
                '2020-01-03': 0,
                '2020-01-04': 0}

        actual = _pct_changes(list(data.items()), days_from_baseline=1)
        expected = {'2020-01-03': -100}

        # 2020-01-04 is omitted. We can't divide by 0.
        self.assertListEqual(actual, list(expected.items()))

    def test_negative_days_from_baseline(self):
        """
        Tests a negative days_from_baseline.
        It is not a valid input, should return [].
        """
        data = {'2020-01-02': 10,
                '2020-01-03': 20,
                '2020-01-04': 40}

        actual = _pct_changes(list(data.items()), days_from_baseline=-2)
        expected = {}

        self.assertListEqual(actual, list(expected.items()))

    def test_days_from_baseline_equals_data_length(self):
        """
        Tests a days_from_baseline equal to len(data).
        There is no calculation to perform, should return [].
        """
        data = {'2020-01-02': 10,
                '2020-01-03': 20,
                '2020-01-04': 30}

        actual = _pct_changes(list(data.items()), days_from_baseline=3)
        expected = {}

        self.assertListEqual(actual, list(expected.items()))

    def test_days_from_baseline_larger_than_data_length(self):
        """
        Tests a chunk_size larger than len(data).
        This is not a valid input. Should return [].
        """
        data = {'2020-01-02': 10,
                '2020-01-03': 20,
                '2020-01-04': 30}

        actual = _pct_changes(list(data.items()), days_from_baseline=4)
        expected = {}

        self.assertListEqual(actual, list(expected.items()))


if __name__ == '__main__':
    unittest.main()

