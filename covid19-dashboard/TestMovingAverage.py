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
from calculate_data import _moving_average


class TestMovingAverage(unittest.TestCase):
    def test_two_day_moving_average(self):
        """
        Simple 2-day moving average with valid ints.
        """
        data = {'2020-01-02': 10,
                '2020-01-03': 20,
                '2020-01-04': 40}

        actual = _moving_average(list(data.items()), chunk_size=2)
        expected = {'2020-01-03': 15,
                    '2020-01-04': 30}

        self.assertListEqual(actual, list(expected.items()))

    def test_zero_and_negative_values(self):
        """
        Tests to make sure that negative values and zeros
        don't cause any issues. They are valid inputs.
        """
        data = {'2020-01-02': -10,
                '2020-01-03': 0,
                '2020-01-04': 0}

        actual = _moving_average(list(data.items()), chunk_size=2)
        expected = {'2020-01-03': -5, '2020-01-04': 0}

        self.assertListEqual(actual, list(expected.items()))

    def test_negative_chunk_size(self):
        """
        Tests a negative chunk_size.
        It is not a valid input, should return [].
        """
        data = {'2020-01-02': 10,
                '2020-01-03': 20,
                '2020-01-04': 40}

        actual = _moving_average(list(data.items()), chunk_size=-2)
        expected = {}

        self.assertListEqual(actual, list(expected.items()))

    def test_chunk_size_equals_data_length(self):
        """
        Tests a chunk_size equal to len(data).
        This is a valid input. Output should contain only one date->value.
        """
        data = {'2020-01-02': 10,
                '2020-01-03': 20,
                '2020-01-04': 30}

        actual = _moving_average(list(data.items()), chunk_size=3)
        expected = {'2020-01-04': 20}

        self.assertListEqual(actual, list(expected.items()))

    def test_chunk_size_larger_than_data_length(self):
        """
        Tests a chunk_size larger to len(data).
        This is not a valid input. Should return [].
        """
        data = {'2020-01-02': 10,
                '2020-01-03': 20,
                '2020-01-04': 30}

        actual = _moving_average(list(data.items()), chunk_size=4)
        expected = {}

        self.assertListEqual(actual, list(expected.items()))


if __name__ == '__main__':
    unittest.main()

