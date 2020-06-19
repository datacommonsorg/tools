import dataCalculator from "./DataCalculator";

// inputData used for several tests.
const inputData = {
    '2020-01-01': {"geoId/01": 1, "geoId/02": 1},
    '2020-01-02': {"geoId/01": 2, "geoId/02": 2},
    '2020-01-03': {"geoId/01": 3, "geoId/02": 3},
    '2020-01-04': {"geoId/01": 4, "geoId/02": 4},
    '2020-01-05': {"geoId/01": 5, "geoId/02": 5},
    '2020-01-06': {"geoId/01": 6, "geoId/02": 6},
    '2020-01-07': {"geoId/01": 7, "geoId/02": 7},
    '2020-01-08': {"geoId/01": 8, "geoId/02": 8},
    '2020-01-09': {"geoId/01": 10, "geoId/02": 10},
}

/**
 * Checks to make sure that no data input is handled.
 */
test('No input data', () => {
    const range: [string, string] = ['2020-01-01', '2020-01-02']
    const absoluteIncrease: {date: {[geoId: string]: string}} | {} = dataCalculator({}, range, 1, 'difference');
    expect(absoluteIncrease).toEqual({});
});

/**
 * Passing in invalid ISO dates for the range is handled.
 */
test('Invalid ISO dates', () => {
    const range: [string, string] = ['20/19/4590', '2020-01-01']
    const absoluteIncrease: {date: {[geoId: string]: string}} | {} = dataCalculator(inputData, range, 1, 'difference');
    expect(absoluteIncrease).toEqual({});
});

/**
 * Passing in an invalid range is handled.
 * [April 1, February 10] are invalid ranges, for example.
 */
test('Invalid range', () => {
    const range: [string, string] = ['2020-01-01', '2010-01-01']
    const absoluteIncrease: {date: {[geoId: string]: string}} | {} = dataCalculator(inputData, range, 1, 'difference');
    expect(absoluteIncrease).toEqual({});
});

/**
 * Requesting a calculation with no data for a geoId for a specific date, is handled.
 */
test('Sometimes there is no data for a given geoId', () => {
    const inputData = {
        '2020-01-01': {"geoId/01": 1, "geoId/02": 1},
        '2020-01-02': {"geoId/01": 2, "geoId/02": 3},
        '2020-01-03': {"geoId/01": 3, "geoId/02": 3},
        '2020-01-04': {"geoId/01": 4},
        '2020-01-05': {"geoId/01": 5, "geoId/02": 5},
        '2020-01-06': {"geoId/01": 6, "geoId/02": 6},
    }
    const range: [string, string] = ['2020-01-01', '2020-01-06']
    const absoluteIncrease: {date: {[geoId: string]: string}} | {} = dataCalculator(inputData, range, 1, 'difference');
    expect(absoluteIncrease).toEqual({
        '2020-01-02': {'geoId/01': 1, 'geoId/02': 2},
        '2020-01-03': {'geoId/01': 1, 'geoId/02': 0},
        '2020-01-04': {'geoId/01': 1},
        '2020-01-05': {'geoId/01': 1},
        '2020-01-06': {'geoId/01': 1, 'geoId/02': 1}
    });
});

/**
 * Requesting perCapita with no population, is handled.
 */
test('No population as input for perCapita', () => {
    const range: [string, string] = ['2020-01-05', '2020-01-09']
    const absoluteIncrease: {date: {[geoId: string]: string}} | {} = dataCalculator(inputData, range, 1, 'perCapita');
    expect(absoluteIncrease).toEqual({});
});

/**
 * Performs a single-day difference calculation and makes sure output is expected.
 */
test('Simple difference calculation', () => {
    const range: [string, string] = ['2020-01-05', '2020-01-09']
    const absoluteIncrease: {date: {[geoId: string]: string}} | {} = dataCalculator(inputData, range, 1, 'difference');
    expect(absoluteIncrease).toEqual({
        '2020-01-05': {'geoId/01': 1, 'geoId/02': 1},
        '2020-01-06': {'geoId/01': 1, 'geoId/02': 1},
        '2020-01-07': {'geoId/01': 1, 'geoId/02': 1},
        '2020-01-08': {'geoId/01': 1, 'geoId/02': 1},
        '2020-01-09': {'geoId/01': 2, 'geoId/02': 2},
    });
});

/**
 * Performs a single-day increase calculation and makes sure output is expected.
 */
test('Simple increase calculation', () => {
    const inputData: {date: {geoId: string}} | {} =
        {"2020-01-05": {"geoId/01": 1, "geoId/02": 1, 'geoId/03': 10},
        "2020-01-06": {"geoId/01": 2, "geoId/02": 0, 'geoId/03': 10}}
    const range: [string, string] = ['2020-01-05', '2020-01-09']
    const absoluteIncrease: {date: {[geoId: string]: string}} | {} = dataCalculator(inputData, range, 1, 'difference');
    expect(absoluteIncrease).toEqual({
        '2020-01-06': {'geoId/01': 1, 'geoId/02': -1, 'geoId/03': 0},
    });
});

/**
 * Performs a single-day perCapita calculation and makes sure output is expected.
 */
test('Simple perCapita calculation', () => {
    const population = {"geoId/01": 5, "geoId/02": 10}
    const range: [string, string] = ['2020-01-05', '2020-01-09']
    const absoluteIncrease: {date: {[geoId: string]: string}} | {} = dataCalculator(inputData, range, 1, 'perCapita', population);
    expect(absoluteIncrease).toEqual({
        '2020-01-05': {'geoId/01': 0.2, 'geoId/02': 0.1},
        '2020-01-06': {'geoId/01': 0.2, 'geoId/02': 0.1},
        '2020-01-07': {'geoId/01': 0.2, 'geoId/02': 0.1},
        '2020-01-08': {'geoId/01': 0.2, 'geoId/02': 0.1},
        '2020-01-09': {'geoId/01': 0.4, 'geoId/02': 0.2},
    });
});

/**
 * Performs a single-day absolutePerCapita calculation and makes sure output is expected.
 */
test('Simple absolutePerCapita calculation', () => {
    const population = {"geoId/01": 5, "geoId/02": 10}
    const range: [string, string] = ['2020-01-05', '2020-01-09']
    const absoluteIncrease: {date: {[geoId: string]: string}} | {} = dataCalculator(inputData, range, 1, 'absolutePerCapita', population);
    expect(absoluteIncrease).toEqual({
        '2020-01-05': {'geoId/01': 1, 'geoId/02': 0.5},
        '2020-01-06': {'geoId/01': 1.2, 'geoId/02': 0.6},
        '2020-01-07': {'geoId/01': 1.4, 'geoId/02': 0.7},
        '2020-01-08': {'geoId/01': 1.6, 'geoId/02': 0.8},
        '2020-01-09': {'geoId/01': 2, 'geoId/02': 1},
    });
});

/**
 * Check to make sure that passing in a negative population will trigger that geoId to be ignored.
 */
test('absolutePerCapita calculation with negative population', () => {
    const population = {"geoId/01": 5, "geoId/02": -10}
    const range: [string, string] = ['2020-01-05', '2020-01-09']
    const absoluteIncrease: {date: {[geoId: string]: string}} | {} = dataCalculator(inputData, range, 1, 'absolutePerCapita', population);
    expect(absoluteIncrease).toEqual({
        '2020-01-05': {'geoId/01': 1},
        '2020-01-06': {'geoId/01': 1.2},
        '2020-01-07': {'geoId/01': 1.4},
        '2020-01-08': {'geoId/01': 1.6},
        '2020-01-09': {'geoId/01': 2},
    });
});
