/**
 * Copyright 2020 Google LLC
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
import {shouldReadLine} from './ParseMCF.js';

const csv = require('csvtojson');

/**
 * Returns the string following '->' in  a given string. Used for getting csv
 * column name when filling in tmcf with values from csv.
 * Ex:   C:SomeDataset->GeoId would return 'GeoId'
 * @param {string} propValue The string to look for a column name in.
 * @return {string|null} The column name that comes after '->'.
 */
function getArrowId(propValue) {
  if (propValue.includes('->')) {
    return propValue.split('->')[1];
  }
  return null;
}

/**
 * Returns a string matching the format E:'DataSet Name'->'Entity #'.
 * @param {string} line The string to look for a match in.
 * @return {string|null} The entity id that matches the specified format.
 */
function getEntityID(line) {
  const localIDMatch = line.match('E:(.*)->(.*)');
  if (localIDMatch) {
    return localIDMatch[0];
  }
  return null;
}

/**
 * Generates a local id for a node of specfic row in csv from an entity id used
 * in tmcf file.
 * Ex: E:SomeDataset->E1 => SomeDataset_E1_R<index>
 * @param {string} entityID The entity id used in tmcf file.
 * @param {string} index The row number in the csv of the node to be created.
 * @return {string|null} The local id for the node of the specific csv row.
 */
function getLocalIDFromEntityID(entityID, index) {
  if (entityID) {
    return 'l:' + entityID.replace('->', '_').replace('E:', '') + '_R' + index;
  }
  return null;
}

/**
 * Converts propertyValues from a line of tmcf to mcf by either converting
 * entity ids to local ids or replacing a csv column reference with the actual
 * value from the csv.
 *
 * @param {string} propValues The property values from the line of TMCF.
 * @param {Object} csvRow The JSON representation of a single row of a csv file.
 *     The keys are the column names and values are the corresponding entries of
 *     the csv for the specfic row/column.
 * @param {number} index The row number of the csvRow, used to generate a local
 *     id if needed.
 * @return {string} The mcf version of the given propValues which has local ids
 *     in lieu of entity ids and csv column references replaces with csv values.
 */
function parsePropertyValues(propValues, csvRow, index) {
  const parsedValues = [];

  for (const propValue of propValues.split(',')) {
    let parsedValue = propValue;

    const entityID = getEntityID(propValue);

    // convert entity id format to local id format
    // Ex: E:SomeDataset->E1 => SomeDataset_E1_R<index>
    if (entityID) {
      const localID = getLocalIDFromEntityID(entityID, index);
      parsedValue = parsedValue.replace(entityID, localID);
    } else {
      // Replace csv column placeholder with the value
      const colName = getArrowId(propValue);
      parsedValue = parsedValue.replace(/C:(.*)->(.*)/, csvRow[colName]);
    }
    parsedValues.push(parsedValue);
  }
  return parsedValues.join(',');
}

/**
 * Convert a row of csv to mcf using the tmcf as a template.
 * @param {string} template The string representation of tmcf file.
 * @param {Object} csvRow The JSON representation of a single row of a csv file.
 *     The keys are the column names and values are the corresponding entries of
 *     the csv for the specfic row/column.
 * @param {number} index The row number of the csvRow, used to generate a local
 *     id if needed.
 * @return {string} The constructed mcf for the single row from csv file.
 */
function fillTemplateFromRow(template, csvRow, index) {
  const filledTemplate = [];
  for (const line of template.split('\n')) {
    if (!line.trim()) {
      filledTemplate.push('');
      continue;
    }

    if (!shouldReadLine(line)) continue;

    const propLabel = line.split(':')[0];
    const propValues = line.replace(propLabel + ':', '').trim();

    const parsedValues = parsePropertyValues(propValues, csvRow, index);

    filledTemplate.push(propLabel + ': ' + parsedValues);
  }
  return filledTemplate.join('\n');
}

/**
 * Creates an mcf string from a string representation of TMCF file and the json
 * representation of a CSV file. The tmcf is populated with csv files for each
 * row of the csv.
 * @param {string} template The string representation of a tmcf file.
 * @param {Array<Object>} csvRows The json representation of the csv file. Each
 *     Object element of the array represents one row of the csv.
 * @return {string} The created mcf as a string.
 */
function csvToMCF(template, csvRows) {
  let index = 1;
  const mcfStrList = [];
  for (const row of csvRows) {
    mcfStrList.push(fillTemplateFromRow(template, row, index));
    index += 1;
  }
  return mcfStrList.join('\n');
}

/**
 * Converts CSV file to an array of JS Object where each JS Object in the array
 * represents one row of the csv. The keys of the object are the column header
 * names and the values of the object are the csv entries in that column of the
 * given row the object represents.
 * @param {string} template The string representation of a tmcf file.
 * @param {FileObject} csvFile THe csv file from html file-input element.
 * @return {Array<Object>} The json representation of the csv file.
 */
async function readCSVFile(template, csvFile) {
  const fileReader = new FileReader();
  fileReader.readAsText(csvFile);
  return new Promise((res, rej) => {
    fileReader.addEventListener('loadend', (result) => {
      csv().fromString(fileReader.result).then((csvRows) => {
        const mcf = csvToMCF(template, csvRows);
        res(mcf);
      });
    });
    fileReader.addEventListener('error', rej);
  });
}

/**
 * Reads a tmcf file and returns the contents as a string
 * @param {FileObject} tmcfFile The tmcf file from html file-input element.
 * @return {string} The string representation of the tmcf file.
 */
async function readTMCFFile(tmcfFile) {
  const fileReader = new FileReader();
  fileReader.readAsText(tmcfFile);
  return new Promise((res, rej) => {
    fileReader.addEventListener('loadend', (result) => {
      res(fileReader.result);
    });
    fileReader.addEventListener('error', rej);
  });
}


/**
 * Converts a TMCF file and CSV file to an MCF string.
 * @param {FileObject} tmcfFile The tmcf file from html file-input element.
 * @param {FileObject} csvFile THe csv file from html file-input element.
 * @return {string} The translated mcf as a string.
 */
async function tmcfCSVToMCF(tmcfFile, csvFile) {
  return readTMCFFile(tmcfFile)
      .then((template) => readCSVFile(template, csvFile));
}

export {
  tmcfCSVToMCF, csvToMCF, fillTemplateFromRow, getLocalIDFromEntityID,
  getEntityID, getArrowId, parsePropertyValues
};
