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

from datetime import datetime, timedelta

from typing import Union


def _moving_average(date_to_val: dict, chunk: int = 7) -> dict:
    """
    Method allows us to calculate the time-series average on a dictionary.
    :param date_to_val: a dictionary where date->int.
    :param chunk: number of days to take the average of. 1 week is the default.
    :return: a new dictionary, date->int where date is the average
    of the previous chunk days.
    """
    # If there are less elements than our chunk_size, then exit.
    # We can't perform any calculations.
    if len(date_to_val.keys()) <= chunk:
        return {}

    # Get a list of [Key, Value].
    # Key = date, Value = cases/deaths.
    values: list = list(date_to_val.items())
    # Sort the values by date, e[0].
    values.sort(key=lambda e: e[0])

    # Sum the first numbers from 0 to chunk_size.
    total: int = sum(value for key, value in values[:chunk])

    output: dict = {}

    # We move in sizes of chunk_size, storing the sum from n to n+chunk_size
    # on output[date]. Every movement, we subtract the first element
    # and add the last element. Similar to how a queue works,
    # remove the first add to end.
    for i in range(chunk, len(values)):
        date, value = values[i]
        # Add the current value and subtract the oldest value from the list.
        total += value - values[i - chunk][1]
        # Get the current average.
        average: float = total / chunk
        # Store the average for this date under output[date].
        output[date] = average

    return output


def _clean_dataset(date_to_val: dict,
                   step_size: int = 2,
                   start_date: str = '2020-03-01'):
    """
    Given a dataset, return the elements whose index is divisible by step_size.
    Remove any negative values and dates starting prior to start_date.
    :param start_date: any date before this date will be omitted.
    :param date_to_val: an object of type date->int.
    :param step_size: the size of our steps.
    :return: the same dataset but 1/nth of the size.
    """
    # The latest date is the largest date from the list of dates.
    latest_date: str = max(list(date_to_val.keys()))

    # Get a list of (Key, Value).
    # Key = date, Value = cases/deaths.
    date_to_val_list = list(date_to_val.items())
    # Sort the values by date, elem[0].
    date_to_val_list = sorted(date_to_val_list, key=lambda e: e[0])

    # Only include the element if its index is divisible by chunk.
    date_to_val_list = date_to_val_list[::step_size]

    # Remove dates before March 1st.
    date_to_val_list = [
        (date, value)
        for date, value in date_to_val_list
        if date >= start_date
    ]

    # Remove negative values from the list.
    date_to_val_list = [
        (date, 0) if value < 0 else (date, value)
        for date, value in date_to_val_list
    ]

    # Because the latest date might have been skipped by the step_size.
    # Check to see if it's in our dataset, otherwise append it.
    # We need the latest date to be present.
    if date_to_val_list[-1][0] != latest_date:
        date_to_val_list.append((latest_date, date_to_val[latest_date]))

    # Convert the list of (date, value) back to a dictionary.
    output = dict(date_to_val_list)

    return output


def calculate_data(data_type: str, data: dict, population: int) -> dict:
    """
    Given a dataset for a region and its population,
    perform different types of calculations on every date.
    :param data_type: type of data, "cases" or "deaths".
    :param data: a dictionary containing date->int.
    :param population: geoId -> population.
    :return: a dictionary with the 7-week moving average + other calculations.
    """
    # For example, 1-week moving average.
    chunk_size: int = 7

    # Instantiate the variables to {} or None depending on data type.
    week_ave: dict = {}
    week_ave_value: Union[float, None] = None
    per_capita: dict = {}
    per_capita_value: Union[float, None] = None
    pct_increase_value: Union[float, None] = None

    # If there are less elements than our chunk_size.
    # We can't perform any calculations.
    if len(data.keys()) > chunk_size:
        # The latest date is the largest date from the list of dates.
        latest_date: str = max(list(data.keys()))

        # Calculate the time-series moving average.
        week_ave: dict = _moving_average(data, chunk=chunk_size)
        # Get the value for the current date.
        week_ave_value: int = week_ave[latest_date]

        # If population is larger than 0, perform the division on dataset.
        if population > 0:
            per_capita: dict = {
                key: (week_ave[key] / population) * 1_000_000
                for key in week_ave
            }
            per_capita_value: float = per_capita[latest_date]

        # Calculate the latest_date - 7 days.
        date_1_week_ago: datetime = \
            datetime.fromisoformat(latest_date) - timedelta(days=7)
        date_1_week_ago: str = date_1_week_ago.strftime('%Y-%m-%d')

        # If the date 1 week ago is present in the dataset.
        if date_1_week_ago in week_ave:
            # Get the value for that date.
            week_ave_1w_value: int = week_ave[date_1_week_ago]
            # If the value is larger than 0, perform pct change.
            if week_ave_1w_value > 0:
                pct_increase_value: float = \
                    ((week_ave_value / week_ave_1w_value) - 1) * 100

        # Only keep even indices.
        # This step is done to improve file size.
        week_ave = _clean_dataset(week_ave, 2)
        per_capita = _clean_dataset(week_ave, 2)

    output: dict = {
        '7DayAverage' + data_type: week_ave,
        '7DayAverage' + data_type + 'Value': week_ave_value,
        'perCapita' + data_type: per_capita,
        'perCapita' + data_type + 'Value': per_capita_value,
        'pctChange' + data_type + 'Value': pct_increase_value
    }

    return output
