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
import {Series, SeriesObject, TimeDataObject} from './time-series';
import {shouldReadLine} from './utils';

interface Properties {
  [property: string]: string;
}

interface CsvRow {
  [header: string]: string | number;
}

interface ParsedCsvRow {
  facet: string;
  date: string;
  value: string;
  mcf: string
}

interface ParsedCsv {
  otherMcfs: string[];
  datapoints: TimeDataObject;
}

interface ParsedTemplate {
  dataEntities: string[];
  otherEntities: string[];
}

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
 * @param {CsvRow} csvRow The JSON representation of a single row of a csv
 *     file. The keys are the column names and values are the corresponding
 *     entries of the csv for the specfic row/column.
 * @return {string} The mcf version of the given propValues which has local
 *     ids in lieu of entity ids and csv column references replaces with csv
 *     values.
 */
  fillPropertyValues(propValues: string, csvRow: CsvRow) : string {
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
 * Convert a single row to an object containining its facet
 * and its corresponding value, date, and other properties
 * @param {string} template The string representation of a tmcf file.
 * @param {CsvRow} row The json representation of the csv row.
 *     Each CsvRow element of the array represents one row of the csv.
 * @return {ParsedCsvRow | null} an object containing the facet, date,
 *     value, and other additional properties
 */
  getFacetAndValueFromRow(template: string, row: CsvRow)
  : ParsedCsvRow | null {
    const properties: Properties = {};

    // Parse row
    for (const line of template.split('\n')) {
      if (!line.trim() || !shouldReadLine(line)) {
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
          properties[propLabel] =
              this.getLocalIdFromEntityId(entityID) as string;
        } else {
          properties[propLabel] = propValues;
        }
      } else {
        const filledValues = this.fillPropertyValues(propValues, row);
        properties[propLabel] = filledValues;
      }
    }

    // Ignore non-StatVarObservations
    if (!properties.typeOf || properties.typeOf !== 'dcs:StatVarObservation') {
      return null;
    }

    // Generate output
    const facet = Series.toID(
        properties.variableMeasured,
        properties.observationAbout,
        properties.provenance,
        properties.measurementMethod,
        properties.observationPeriod,
        properties.unit,
        properties.scalingFactor ?
          parseFloat(properties.scalingFactor) : undefined,
    );
    const date = properties.observationDate ? properties.observationDate : '';
    const value = properties.value ? properties.value : '';

    const propertyPairs = [];
    for (const property of Object.keys(properties)) {
      propertyPairs.push(`${property}: ${properties[property]}`);
    }
    const mcf = propertyPairs.join('\n');

    return {facet, date, value, mcf};
  }


  /**
 * Creates a mapping from facet to values from a string representation of
 * TMCF file and the json representation of a CSV file. The whole
 * template from the tmcf is populated with values for each row of the csv.
 * @param {string} template The string representation of a tmcf file.
 * @param {Array<CsvRow>} csvRows The json representation of the csv file.
 *     Each CsvRow element of the array represents one row of the csv.
 * @return {ParsedCsv} An object containing the parsed datapoints and mcf
 * strings
 */
  parseCsvRows(template: string, csvRows: CsvRow[]) : ParsedCsv {
    this.csvIndex = 1;

    // Split tmcf file into StatVarObs entities and non-StatVarObs entities
    const {dataEntities, otherEntities} =
        ParseTmcf.getEntityTemplates(template);

    const datapoints: TimeDataObject = {};
    const otherMcfs = otherEntities;

    for (const row of csvRows) {
      for (const entityTemplate of dataEntities) {
        const parsedCsvRow = this.getFacetAndValueFromRow(
            entityTemplate,
            row,
        );

        if (parsedCsvRow) {
          const {facet, date, value, mcf} = parsedCsvRow;
          const parsedValue = value !== '' ? parseFloat(value) : undefined;
          const datapoint = {
            mcf,
            value: parsedValue,
          };

          // Add
          const seriesObject = datapoints[facet] ?
              datapoints[facet] as SeriesObject : {};
          seriesObject[date] = datapoint;
          datapoints[facet] = seriesObject;
        }
      }
      this.csvIndex += 1;
    }
    return {datapoints, otherMcfs};
  }

  /**
  * Turns a CSV string array to a CsvRow object
  * @param {string[]} lines an array of lines where each line is a row
  * of the csv
  * @return {CsvRow[]} an array of objects with keys as column names and
  * values as the corresponding row value
  */
  static convertCsvToJson(lines: string[]) : CsvRow[] {
    const headers = lines.length > 0 ?
    lines.shift()?.split(',') as string[] : [];

    return lines.map((line) => {
      const values = line.trim().split(',');
      const output: CsvRow = {};

      for (let i = 0; i < values.length; i++) {
        output[headers[i]] = values[i];
      }
      return output;
    });
  }

  /**
 * Converts CSV file to an object containing the data points and their
 * mcf strings
 * @param {string} template The string representation of a tmcf file.
 * @param {FileObject} csvFile The csv file from html file-input element.
 * @return {ParsedCsv} An object containing the parsed datapoints and mcf
 * strings
 */
  async parseCsv(
      template: string, csvFile: Blob,
  ) : Promise<ParsedCsv> {
    const fileReader = new FileReader();
    fileReader.readAsText(csvFile);

    return new Promise((res, rej) => {
      fileReader.addEventListener('loadend', () => {
        const lines = (fileReader.result as string).split('\n');
        const csvRows = ParseTmcf.convertCsvToJson(lines);

        res(this.parseCsvRows(template, csvRows));
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
 * Splits a tmcf file string into StatVarObservation entity strings and
 * other entity strings
 * @param {string} template the string representation of a tmcf file
 * @return {ParsedTemplate} an object that sorts each entity string into
 * either a statVarObs (data) entity or other entity
 */
  static getEntityTemplates(template: string): ParsedTemplate {
    const templates: ParsedTemplate = {
      dataEntities: [],
      otherEntities: [],
    };

    const lines = template.split(/\r?\n/);

    let current = '';
    let currentIsStatVarObs = false;

    for (let line of lines) {
      line = line.trim();

      // If a new entity block has started, add current string
      // and reset all values
      if (line.startsWith('Node')) {
        // Only add if the string is not empty
        if (current.trim() !== '') {
          if (currentIsStatVarObs) {
            templates.dataEntities.push(current.trim());
          } else {
            templates.otherEntities.push(current.trim());
          }
        }

        // Reset values
        current = '';
        currentIsStatVarObs = false;
      } else if (line.startsWith('typeOf')) {
        const index = line.indexOf(':');
        const type = line.slice(index + 1).trim();

        currentIsStatVarObs = type === 'dcs:StatVarObservation';
      }

      current += line + '\n';
    }

    // Add current entity
    if (current.trim() !== '') {
      if (currentIsStatVarObs) {
        templates.dataEntities.push(current.trim());
      } else {
        templates.otherEntities.push(current.trim());
      }
    }

    return templates;
  }

  /**
 * Converts a TMCF file and CSV file to a set of datapoints and mcf strings
 * @param {FileObject} tmcfFile The tmcf file from html file-input element.
 * @param {FileObject} csvFile THe csv file from html file-input element.
 * @return {ParsedCsv} An object containing the parsed datapoints and mcf
 * strings
 */
  static async parseTmcfAndCsv(tmcfFile: Blob, csvFile: Blob)
  : Promise<ParsedCsv> {
    return ParseTmcf.readTmcfFile(tmcfFile).then(
        (template: string | ArrayBuffer | null) => {
          const tmcfParser = new ParseTmcf();
          return tmcfParser.parseCsv(template as string, csvFile);
        },
    );
  }
}

export {ParseTmcf};
