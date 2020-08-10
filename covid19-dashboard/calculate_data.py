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

from typing import Dict, Tuple, List

DateToValueDictType = Dict[str, float]
DateToValueListType = List[Tuple[str, float]]


def _difference(date_to_value: DateToValueListType,
                n_difference: int):
    # n_difference can't be negative.
    # We can't perform the difference of a negative n_difference.
    if n_difference <= 0:
        return []

    # If there are less elements than our n_difference, then exit.
    # We can't perform the calculation.
    if len(date_to_value) <= n_difference:
        return []

    # Sort the data by the date, that is, elem[0].
    sorted_date_to_value = sorted(date_to_value, key=lambda elem: elem[0])

    output = []

    for i in range(n_difference, len(sorted_date_to_value)):
        date, value = sorted_date_to_value[i]
        prev_value = sorted_date_to_value[i - n_difference][1]
        difference = value - prev_value
        output.append((date, difference))
    return output


def _moving_average(date_to_val: DateToValueListType,
                    chunk_size: int = 7) -> DateToValueListType:
    """
    Method allows us to calculate the time-series average on our dataset.
    :param date_to_val: a list of tuples of type of (date, value).
    date type is a string in ISO-8601. Example: "2020-01-02"
    :param chunk_size: number of days to take the average of.
    :return: a new list of tuples of type of (date, value)
    where each date contains the average
    of the previous N-chunk_size days.
    """
    # chunk_size can't be negative.
    # We can't perform the moving average of negative chunk_size.
    if chunk_size <= 0:
        return []

    # If there are less elements than our chunk_size, then exit.
    # We can't perform any calculations.
    if len(date_to_val) < chunk_size:
        return []

    # Sort the data by the date, that is, elem[0].
    date_to_value_list = sorted(date_to_val, key=lambda elem: elem[0])

    # Sum the first numbers from 0 to chunk_size.
    total = sum(value for key, value in date_to_value_list[:chunk_size])

    # Moving average for our first date.
    start_date = date_to_value_list[chunk_size - 1][0]
    start_date_average = total / chunk_size

    # Store the moving average for our first date.
    output: DateToValueListType = [(start_date, start_date_average)]

    # Sum the last n-chunk_size values from current date.
    # average = sum / chunk_size
    # Append the average to the end of the array.
    for i in range(chunk_size, len(date_to_value_list)):
        date, value = date_to_value_list[i]
        # Add the current value and subtract the oldest value from the list.
        total += value - date_to_value_list[i - chunk_size][1]
        # Get the current average.
        average = total / chunk_size
        # Store the average for the date at the end of the list output.
        output.append((date, average))

    return output

def _pct_changes(date_to_val: DateToValueListType,
                 days_from_baseline: int = 7) -> DateToValueListType:
    """
    Given a dataset, calculate the percent change of days_apart for all dates.
    Return a new list where each date contains that date's percent
    changes from date - days_apart_date.
    :param date_to_val: a list of tuples: (date, value).
    date type is a string in ISO-8601. Example: "2020-01-02"
    :param days_from_baseline: the number of days from the baseline date.
    baseline_date = date - days_from_baseline
    :return: a new list of tuples of type of (date, value)
    where each date contains the pct_change from the baseline_date.
    """

    # days_from_baseline can't be 0 or negative.
    if days_from_baseline <= 0:
        return []

    # If date_to_val is less than days_from_baseline return [].
    # We can't calculate the pct change from a date we have no data for.
    if len(date_to_val) <= days_from_baseline:
        return []

    # Sort the values by the date found in elem[0].
    date_to_val = sorted(date_to_val, key=lambda elem: elem[0])

    pct_changes_list: DateToValueListType = []

    # Start from days_from_baseline.
    for i in range(days_from_baseline, len(date_to_val)):
        # baseline_date = Current date - days_from_baseline
        _, baseline_value = date_to_val[i - days_from_baseline]
        # the current date we are observing.
        date, value = date_to_val[i]

        # Division by 0 is not allowed.
        # If baseline_value is 0, append None for that date instead.
        if baseline_value == 0:
            continue

        # percent change from baseline_date to date.
        # Adjusted to percent (multiply by 100).
        pct_change_value = ((value / baseline_value) - 1) * 100
        # Add to the back of the list, in order.
        pct_changes_list.append((date, pct_change_value))

    return pct_changes_list


def _clean_dataset(date_to_value: DateToValueListType,
                   step_size: int = 2,
                   keep_negatives: bool = False) -> DateToValueListType:
    """
    Given a date_to_val, filter out data and sort it by date.
    Remove negative values, if requested.
    Only return the last 100 dates in the dataset.
    Remove indices not divisible by step_size.
    :param date_to_value: a list of tuples: (date, value).
    date type is a string in ISO-8601. Example: "2020-01-02"
    :param step_size: if an index is not divisible by step_size, drop it.
    Only index divisible by step_size will be kept.
    :return: the same dataset but 1/nth of the size.
    """
    # If date_to_val has no data, return [].
    if not date_to_value:
        return []

    # Sort the values by the date found in elem[0].
    date_to_value_list = sorted(date_to_value, key=lambda elem: elem[0])

    # Only include dates in the last 100 days.
    date_to_value_list: DateToValueListType = date_to_value_list[-100:]

    # Keep a real copy of the last 7 days in the dataset.
    original_copy_last_7d: DateToValueListType = date_to_value_list[-7:]

    # Only include the element if its index is divisible by step_size.
    # This filtering is done to reduce the size of the output.
    filtered_dataset: DateToValueListType = date_to_value_list[:-7:step_size]

    # Combine filtered dataset and original's dataset's last 7 days.
    # We want to keep the original quality of the last 7 days.
    combined_dataset = filtered_dataset + original_copy_last_7d

    # If keep_negatives requested, return.
    if keep_negatives:
        return combined_dataset

    # Otherwise, replace negative values with 0s.
    dataset_without_negatives = [(date, 0) if value < 0 else (date, value)
                                 for date, value in combined_dataset]

    return dataset_without_negatives


def calculate_data(cumulative_stats: DateToValueDictType,
                   population: int,
                   moving_average_chunk_size: int = 7
                   ) -> Dict[str, DateToValueDictType]:
    """
    Given a dataset for a region and its population,
    perform different types of calculations for every date.
    :param moving_average_chunk_size: In days. Defaults to 7 days.
    The size of the window to take the moving average of.
    :param cumulative_stats: a dictionary containing date->int.
    date type is a string in ISO-8601. Example: "2020-01-02"
    :param population: a integer representing the population.
    NOTE: for return type documentation, please see README.md's APIs section.
    :return: a dictionary containing calculations of
    movingAverage, perCapita and pctIncrease.
    """
    # The population is required.
    # If population is invalid, return nothing.
    if not population or population <= 0:
        return {}

    # If there are less elements than our CHUNK_SIZE.
    # We can't perform any calculations.
    if len(cumulative_stats.keys()) <= moving_average_chunk_size:
        return {}

    # Convert the moving_average to a list of tuples.
    # We want to sort by date. Tuples will help us.
    # Where each {date: value} becomes (date, value).
    cumulative_list = list(cumulative_stats.items())

    # Sort the data by the date, that is, elem[0].
    date_to_value_list = sorted(cumulative_list, key=lambda elem: elem[0])

    difference_list = _difference(date_to_value_list, 1)

    # Calculate the time-series moving average.
    moving_averages_list = _moving_average(difference_list,
                                           moving_average_chunk_size)

    # Divide all values by the place's population.
    # Multiply by 1M to amplify solution.
    # Repeat for all dates.
    per_capitas_list: DateToValueListType = [
        (date, (value / population) * 1_000_000)
        for date, value in moving_averages_list
    ]

    # Calculate the percent changes for every day since the previous week.
    pct_changes_list = _pct_changes(moving_averages_list, 7)

    # Only keep even indices.
    # This filtering is done to improve file size.
    # Convert list of tuples back to a dictionary.
    # (date, value) converts to {date: value}.
    # Only keep negative values for cumulatives and pct_changes.
    cumulatives = dict(_clean_dataset(cumulative_list, 3, True))
    moving_averages = dict(_clean_dataset(moving_averages_list, 3, False))
    per_capitas = dict(_clean_dataset(per_capitas_list, 3, False))
    pct_changes = dict(_clean_dataset(pct_changes_list, 3, True))

    output: Dict[str, DateToValueDictType] = {
        'cumulative': cumulatives,
        'movingAverage': moving_averages,
        'perCapita': per_capitas,
        'pctChange': pct_changes
    }

    return output
