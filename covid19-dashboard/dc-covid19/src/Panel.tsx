/**
 Copyright 2020 Google LLC

 Licensed under the Apache License, Version 2.0 (the "License");
 you may not use this file except in compliance with the License.
 You may obtain a copy of the License at

 https://www.apache.org/licenses/LICENSE-2.0

 Unless required by applicable law or agreed to in writing, software
 distributed under the License is distributed on an "AS IS" BASIS,
 WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 See the License for the specific language governing permissions and
 limitations under the License.
 */

import React from 'react';
import ContentFile from './ChartsConfiguration.json';
import moment from 'moment';

import EmptyPanel from './EmptyPanel';
import {addNDaysToDate, getRangeOfDates} from './Utils';
import Graph from './Graph';
import calculate from './DataCalculator';
import generateMetadata from './MetaDataGenerator';

type Props = {
  allData: any[];
  region: string;
  datePicked: string;
  selectedShowTopN: number;
  panelId: string;
};

type Metadata = {
  geoId: string;
  name: string;
  onHoverInfo: string[];
  textOnTopOfBar: string;
  value: number;
};

type DateToGeoIdToValue = {[date: string]: {geoId: number}} | {};
type DateToGeoIdToMetadata = {[date: string]: {geoId: number}} | {};

export default function Panel(props: Props) {
  const panelContent = ContentFile[props.panelId];
  const label: string = panelContent.label;
  const deltaDays: number = panelContent.deltaDays;
  const calculationType: string[] = panelContent.calculationType;

  // inputData is different for cases or deaths.
  let inputData: DateToGeoIdToValue;
  if (label === 'cases') {
    inputData = props.allData[0];
  } else {
    inputData = props.allData[1];
  }
  const geoIdToPopulation: {[geoId: string]: number} = props.allData[2];
  const geoIdToName: {[geoId: string]: string} = props.allData[3];
  const rangeOfDates = getRangeOfDates(props.datePicked, deltaDays);

  // startDate is updated on iteration, hence why "let" is used
  let startDate = moment(rangeOfDates[0]);
  const endDate = moment(rangeOfDates[1]);

  // calculatedData holds our data.
  const calculatedData: DateToGeoIdToValue = {};
  // absoluteData holds our absolute data (either difference or raw)
  const absoluteData: DateToGeoIdToValue = {};

  // From startDate to endDate, perform calculationType
  while (startDate <= endDate) {
    // convert date to isoFormat, since data is stored as such
    const date = startDate.format('YYYY-MM-DD');
    calculatedData[date] = {};
    absoluteData[date] = {};

    for (const geoId in inputData[date]) {
      const dateMinusDeltaDays = addNDaysToDate(date, -deltaDays);
      const valueDeltaDaysAgo = inputData[dateMinusDeltaDays][geoId];
      const valueCurrentDate = inputData[date][geoId];
      // Perform the calculationType on the input data.
      const result = calculate(
        [valueDeltaDaysAgo, valueCurrentDate],
        calculationType
      );

      // absolutePerCapita takes the raw absolute number instead of the difference
      const absolutePerCapita = ['absolute', 'perCapita'].every(v =>
        calculationType.includes(v)
      );

      // The absolute increase (difference) is necessary to show on-hover info
      let absolute: number | null;

      // If the calculation is absolutePerCapita
      // Let's store the raw cumulative value instead of the difference
      if (absolutePerCapita) {
        absolute = valueCurrentDate;
      } else {
        absolute = calculate(
          [valueDeltaDaysAgo, valueCurrentDate],
          ['difference']
        );
      }

      // Make sure that the result is valid
      if (result || result === 0) {
        // Store the result for this observation
        calculatedData[date][geoId] = result;
        // Store the absolute value for this observation
        absoluteData[date][geoId] = absolute;
      }
    }
    startDate = startDate.add(1, 'days');
  }

  // If perCapita then then divide all results by the geoId's population
  if (calculationType.includes('perCapita')) {
    for (const date in calculatedData) {
      for (const geoId in calculatedData[date]) {
        const result = calculatedData[date][geoId] / geoIdToPopulation[geoId];
        // Make sure that the division is valid
        if (result) {
          calculatedData[date][geoId] = result;
        }
      }
    }
  }

  // Generate the metadata for the graph
  // This includes on-hover, bar text, region names, values, name, etc...
  const metadata: DateToGeoIdToMetadata = generateMetadata(
    calculatedData,
    geoIdToPopulation,
    geoIdToName,
    absoluteData,
    label,
    calculationType
  );

  // We only care about the data for the picked date
  const dataForPickedDate: {string: Metadata} = metadata[props.datePicked];

  // If there is data available show charts
  if (Object.keys(inputData).length) {
    return (
      <div className={'panel shadow'}>
        <h4 className={'title'}>{panelContent.title}</h4>
        <h6 className={'title'}>{panelContent.subtitle}</h6>
        <Graph
          label={label}
          data={{[props.datePicked]: dataForPickedDate || {}}}
          selectedShowTopN={props.selectedShowTopN}
          type={panelContent.graphType}
          color={label === 'cases' ? '#990001' : 'grey'}
        />
      </div>
    );
  } else {
    // Otherwise, show empty panel
    return <EmptyPanel reason={'loading'} />;
  }
}
