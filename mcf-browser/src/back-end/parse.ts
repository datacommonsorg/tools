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

import {Series} from './data';
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
   datapoints: Object[];
 };

/** Parse files and get the local nodes
  * @param {Array<Blob>} fileList the list of blobs to be parsed
  * @return {ParseFileResponse} an object containing all of the ids of the
  *    subject nodes and the error messages
  */
async function getNodes(fileList: Blob[]) : Promise<ParseFileResponse> {
  const finalReturn: ParseFileResponse = {
    errMsgs: [],
    localNodes: [],
    datapoints: [],
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
        finalReturn['datapoints'] = finalReturn['datapoints'].concat([
          datapoints,
        ]);

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
  * @param {Object[]} datapoints the time series data
  * @return {Series[]} an array of time series in the data
  */
function getTimeData(datapoints: Object[]) : Series[] {
  // Turn from array of objects (one per file) to one big object
  const allData: any = {};
  for (const data of datapoints) {
    const allSeries = Object.keys(data);
    for (const series of allSeries) {
      allData[series] = allData[series] ? allData[series] : {};
      allData[series] = {...allData[series], ...(data as any)[series]};
    }
  }

  // Turn from object to series
  const output = [];
  const allSeries = Object.keys(allData);
  for (const series of allSeries) {
    output.push(parseSeries(series, allData[series]));
  }

  return output;
}

/**
  * Takes in the facet string generated when parsing the file
  * and return an object of type Series
  * @param {string} facet the facet defining the series
  * @param {Object} values the values for the series
  * @return {Series} the datapoint as a Series object
  */
function parseSeries(facet: string, values: Object) : Series {
  const {
    variableMeasured,
    observationAbout,
    provenance,
    measurementMethod,
    observationPeriod,
    unit,
    scalingFactor,
  } = Series.fromID(facet);
  const data = [];
  for (const date of Object.keys(values)) {
    data.push({
      x: date,
      y: parseFloat((values as any)[date]),
    });
  }

  return new Series(
      data,
      variableMeasured,
      observationAbout,
      provenance,
      measurementMethod,
      observationPeriod,
      unit,
      scalingFactor,
  );
}

export {getNodes, getTimeData, parseSeries};
