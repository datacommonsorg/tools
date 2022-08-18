/**
 * Copyright 2022 Google LLC
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

import {Series, SeriesObject, TimeDataObject} from './time-series';
import {ParseMcf} from './parse-mcf';
import {ParseTmcf} from './parse-tmcf';
import {ParsingError, ERROR_MESSAGES} from './utils';

 type ParseFileResponse = {
   /** A list of errors that occurred while parsing
    * the files
    */
   errMsgs: ParsingError[];

   /** A list of the ids of the subject nodes */
   localNodes: string[];

   /** A list of the generated mcf string for
    * each CSV row
    */
   datapoints: TimeDataObject;
 };

 type TimeDataOutput = {
   /** A list of time series data */
   timeData: Series[];

   /** Error messages that occurred while parsing */
   errMsgs: ParsingError[];
 }

 type ParseSeriesOutput = {
  /** A parsed series object */
  series: Series | null;

  /** Error messages that occurred while parsing */
  errMsgs: ParsingError[];
 }

/**
  * Combines two TimeDataObjects into one
  * @param {TimeDataObject} datapoints the current set of all data points
  * @param {TimeDataObject} newData the new set of data points
  * @return {TimeDataObject} a merged set of all data points
  */
function mergeDataPoints(
    datapoints: TimeDataObject,
    newData: TimeDataObject,
) : TimeDataObject {
  // Go through all series and add their data
  const allSeries = Object.keys(newData);

  for (const series of allSeries) {
    datapoints[series] = series in datapoints ?
        {...datapoints[series], ...newData[series]} :
        newData[series];
  }

  return datapoints;
}

/** Parse files and get the local nodes
  * @param {Array<Blob>} fileList the list of blobs to be parsed
  * @return {ParseFileResponse} an object containing all of the ids of the
  *    subject nodes and the error messages
  */
async function getNodes(fileList: Blob[]) : Promise<ParseFileResponse> {
  const finalReturn: ParseFileResponse = {
    errMsgs: [],
    localNodes: [],
    datapoints: {},
  };

  // Find TMCF file, if it exists
  let tmcfFile = null;
  for (const file of fileList) {
    const fileName = (file as File).name;
    const fileExt = fileName.split('.').pop();

    if (fileExt === 'tmcf') {
      if (tmcfFile) {
        // If another TMCF file was found, throw an error
        finalReturn['errMsgs'] = finalReturn['errMsgs'].concat([{
          'file': (tmcfFile as File).name,
          'errs': [
            ['-1', '', ERROR_MESSAGES.MULTIPLE_TMCF],
          ],
        }]);
      }

      tmcfFile = file;
    }
  }


  for (const file of fileList) {
    const fileName = (file as File).name;
    const fileExt = fileName.split('.').pop();

    if (fileExt === 'mcf') {
      const mcfOut = await ParseMcf.readFile(file);

      if (mcfOut['errMsgs'].length !== 0) {
        finalReturn['errMsgs'] = finalReturn['errMsgs'].concat([
          {
            file: fileName,
            errs: mcfOut['errMsgs'],
          },
        ]);
      }

      finalReturn['localNodes'] = finalReturn['localNodes'].concat(
          mcfOut['localNodes'],
      );
    } else if (fileExt === 'csv') {
      if (tmcfFile) {
        const tmcfFileName = (tmcfFile as File).name;
        const tmcfOut = await ParseTmcf.generateMcf(tmcfFile, file).then(
            (mcf) => {
              const mcfParser = new ParseMcf(
                  tmcfFileName + '&' + fileName,
              );
              return mcfParser.parseMcfStr(mcf as string);
            },
        );

        const datapoints = await ParseTmcf.generateDataPoints(tmcfFile, file);
        finalReturn['datapoints'] = mergeDataPoints(
            finalReturn['datapoints'],
            datapoints,
        );

        if (tmcfOut['errMsgs'].length !== 0) {
          finalReturn['errMsgs'] = finalReturn['errMsgs'].concat({
            file: tmcfFileName,
            errs: tmcfOut['errMsgs'],
          });
        }
        finalReturn['localNodes'] = finalReturn['localNodes'].concat(
            tmcfOut['localNodes'],
        );
      }
    }
  }
  return finalReturn;
}

/** Group nodes and find all time series
  * @param {TimeDataObject} datapoints the time series data
  * @return {TimeDataOutput} an object containing an array of
  * time series in the data and any error messages
  */
function getTimeData(datapoints: TimeDataObject) : TimeDataOutput {
  // Turn from object to a list of series
  const output: TimeDataOutput = {
    timeData: [],
    errMsgs: [],
  };

  const allSeries = Object.keys(datapoints);
  for (const series of allSeries) {
    const seriesObject = datapoints[series];
    if (seriesObject) {
      const parsedSeriesObject = parseSeries(series, seriesObject);
      if (parsedSeriesObject.errMsgs.length > 0) {
        // If there was an error, add it
        output.errMsgs =
            output.errMsgs.concat(parsedSeriesObject.errMsgs);
      } else if (parsedSeriesObject.series) {
        // If there is a successfully created Series object, add it
        output.timeData.push(parsedSeriesObject.series);
      }
    }
  }

  return output;
}

/**
  * Takes in the facet string generated when parsing the file
  * and return an object of type Series
  * @param {string} facet the facet defining the series
  * @param {SeriesObject} values the values for the series
  * @return {ParseSeriesOutput} a series object or an error message
  */
function parseSeries(facet: string, values: SeriesObject) : ParseSeriesOutput {
  const {
    variableMeasured,
    observationAbout,
    provenance,
    measurementMethod,
    observationPeriod,
    unit,
    scalingFactor,
  } = Series.fromID(facet);

  // If it's missing variableMeasured or observationAbout, return an error
  if (variableMeasured === '' || observationAbout === '') {
    let errorMessage: string;
    if (variableMeasured === '' && observationAbout === '') {
      errorMessage = 'data point is missing variableMeasured and observationAbout';
    }
    else if (variableMeasured === '') {
      errorMessage = 'data point is missing variableMeasured';
    }
    else {
      errorMessage = 'data point is missing observationAbout';
    }
    const error: ParsingError = {
      file: '',
      errs: [['', facet, errorMessage]]
    }
    return {
      errMsgs: [error],
      series: null,
    };
  }

  const data = [];
  for (const date of Object.keys(values)) {
    data.push({
      x: date,
      y: values[date] as number,
    });
  }

  const series = new Series(
      data,
      variableMeasured,
      observationAbout,
      provenance,
      measurementMethod,
      observationPeriod,
      unit,
      scalingFactor,
  );

  return {
    errMsgs: [],
    series,
  };
}

export {getNodes, getTimeData, parseSeries, mergeDataPoints};
