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
import {shouldReadLine} from './utils';

/**
 * Returns the string following '->' in  a given string. Used for getting csv
 * column name when filling in tmcf with values from csv.
 * Ex:   C:SomeDataset->GeoId would return 'GeoId'
 * @param {string} propValue The string to look for a column name in.
 * @return {string|null} The column name that comes after '->'.
 */
function getColumnId(propValue: string) : string | null {
  const colIdMatch = propValue.match('C:(.*)->(.*)');
  if (colIdMatch) {
    return colIdMatch[0];
  }
  return null;
}

/**
 * Returns a string matching the format E:'DataSet Name'->'Entity #'.
 * @param {string} line The string to look for a match in.
 * @return {string|null} The entity id that matches the specified format.
 */
function getEntityID(line: string) : string | null {
  const localIdMatch = line.match('E:(.*)->(.*)');
  if (localIdMatch) {
    return localIdMatch[0];
  }
  return null;
}

/**
 * Class responsible for converting one TMCF file and one CSV file into an MCF
 * string.
 */
class ParseTmcf {
  /**
   * Current row number of the csv file that is being parsed.
   * @type {number}
   */
  csvIndex: number;

  /**
  * Create a ParseTmcf object which keeps tracks of the current csv row
  * number being parsed.
  */
  constructor() {
    this.csvIndex = -1;
  }

  /**
   * Generates a local id for a node of specfic row in csv from an entity id
   * used in tmcf file. Ex: E:SomeDataset->E1 => SomeDataset_E1_R<index>
   * @param {string} entityID The entity id used in tmcf file.
   * @return {string|null} The local id for the node of the specific csv row.
   */
  getLocalIdFromEntityId(entityID: string) : string | null {
    if (entityID) {
      return entityID.replace('->', '_').replace('E:', '') + '_R' +
             this.csvIndex;
    }
    return null;
  }

  /**
   * Converts propertyValues from a line of tmcf to mcf by either converting
   * entity ids to local ids or replacing a csv column reference with the actual
   * value from the csv.
   *
   * @param {string} propValues The property values from the line of TMCF.
   * @param {Object} csvRow The JSON representation of a single row of a csv
   *     file. The keys are the column names and values are the corresponding
   *     entries of the csv for the specfic row/column.
   * @return {string} The mcf version of the given propValues which has local
   *     ids in lieu of entity ids and csv column references replaces with csv
   *     values.
   */
  fillPropertyValues(propValues: string, csvRow: Object) : string {
    const filledValues = [];

    for (const propValue of propValues.split(',')) {
      let filledValue;

      const entityID = getEntityID(propValue);
      const colId = getColumnId(propValue);

      if (entityID) {
        // convert entity id format to local id format
        // Ex: E:SomeDataset->E1 => l:SomeDataset_E1_R<index>
        const localId = 'l:' + this.getLocalIdFromEntityId(entityID);
        filledValue = propValue.replace(entityID, localId);
      } else if (colId) {
        // Replace csv column placeholder with the value
        const colName = colId.split('->')[1];
        filledValue = propValue.replace(colId, (csvRow as any)[colName]);
      } else {
        filledValue = propValue;
      }
      filledValues.push(filledValue);
    }
    return filledValues.join(',');
  }

  /**
   * Convert a single row from the csv file to multiple lines of mcf by filling
   * in the appropriate values in the tmcf template.
   * @param {string} template The string representation of tmcf file.
   * @param {Object} csvRow The JSON representation of a single row of a csv
   *     file. The keys are the column names and values are the corresponding
   *     entries of the csv for the specfic row/column.
   * @return {string} The constructed mcf for the single row from csv file.
   */
  fillTemplateFromRow(template: string, csvRow: Object) : string {
    const filledTemplate = [];

    for (const line of template.split('\n')) {
      if (!line.trim() || !shouldReadLine(line)) {
        filledTemplate.push('');
        continue;
      }

      const propLabel = line.split(':')[0].trim();
      const propValues = line.substring(line.indexOf(':') + 1).trim();

      if (propLabel === 'Node') {
        if (propValues.includes(',')) {
          throw new Error('cannot have multiple ids for Node declaration');
        }
        const entityID = getEntityID(propValues);
        if (entityID) {
          filledTemplate.push(propLabel + ': ' +
                              this.getLocalIdFromEntityId(entityID));
        } else {
          filledTemplate.push(propLabel + ': ' + propValues);
        }
      } else {
        const filledValues = this.fillPropertyValues(propValues, csvRow);
        filledTemplate.push(propLabel + ': ' + filledValues);
      }
    }
    return filledTemplate.join('\n');
  }

  /**
   * Creates an mcf string from a string representation of TMCF file and the
   * json representation of a CSV file. The whole template from the tmcf is
   * populated with values for each row of the csv.
   * @param {string} template The string representation of a tmcf file.
   * @param {Array<Object>} csvRows The json representation of the csv file.
   *     Each Object element of the array represents one row of the csv.
   * @return {string} The generated mcf as a string.
   */
  csvToMcf(template: string, csvRows: Object[]) : string {
    this.csvIndex = 1;
    const mcfLines = [];
    for (const row of csvRows) {
      mcfLines.push(this.fillTemplateFromRow(template, row));
      this.csvIndex += 1;
    }
    return mcfLines.join('\n');
  }

  /**
   * Converts CSV file to an array of JS Object where each JS Object in the
   * array represents one row of the csv. The keys of the object are the column
   * header names and the values of the object are the csv entries in that
   * column of the given row the object represents.
   * @param {string} template The string representation of a tmcf file.
   * @param {FileObject} csvFile The csv file from html file-input element.
   * @return {string} The mcf string for the csv file.
   */
  async readCsvFile(template: string, csvFile: Blob) : Promise<string> {
    const fileReader = new FileReader();
    fileReader.readAsText(csvFile);
    return new Promise((res, rej) => {
      fileReader.addEventListener('loadend', () => {
        const csv = require('csvtojson');
        csv()
            .fromString(fileReader.result)
            .then((csvRows: Object[]) => {
              res(this.csvToMcf(template, csvRows));
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
  static async readTmcfFile(
      tmcfFile: Blob,
  ): Promise<string | ArrayBuffer | null> {
    const fileReader = new FileReader();
    fileReader.readAsText(tmcfFile);
    return new Promise((res, rej) => {
      fileReader.addEventListener('loadend',
          () => {
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
  static async generateMcf(tmcfFile: Blob, csvFile: Blob) : Promise<string> {
    return ParseTmcf.readTmcfFile(tmcfFile).then(
        (template: string | ArrayBuffer | null) => {
          const tmcfParser = new ParseTmcf();
          return tmcfParser.readCsvFile(template as string, csvFile);
        },
    );
  }
}

export {ParseTmcf};
