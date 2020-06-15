import {numberWithCommas} from "./Utils";
type Metadata = {
    name: string,
    onHoverInfo: string[]
    textOnTopOfBar: string,
    population: number,
}

type DateToGeoIdToValue = {string: {string: number}} | {}

/**
 * Given a list of parameters, return human readable strings explaining the data.
 * @param geoId: the geoId of the region
 * @param regionName: the name of the region
 * @param date: the date of the observation
 * @param value: the value at that specific date for that specific geoId
 * @param population: the total population of that region
 * @param absoluteIncreaseValue: the absolute difference between day 2 and day 1
 * @param label: Are we talking about cases? or deaths?
 * @param contentType: What is the graph showing? Per-Capita? Increase? Absolute?
 */
const getOnHoverInfoText = (geoId: string, regionName: string, date: string, value: number, population: number,
                             absoluteIncreaseValue: number, label: string, contentType: string) => {
    let disclaimer: string = '', onHoverInfo: string[];
    // If it's NYC or Kansas City. Show disclaimer. These are NYT exceptions.
    if (geoId === 'geoId/3651000' || geoId === 'geoId/2938000')
        disclaimer = `All counties in ${regionName} are combined and reported as one.`

    if (contentType === 'perCapita') {
        onHoverInfo = [
            `${value.toFixed(3)} ${label} per 10,000 people`,
            `New ${label}: ${numberWithCommas(absoluteIncreaseValue)}`,
            `Total population: ${numberWithCommas(population)} people`]
    } else if (contentType === 'increase') {
        onHoverInfo = [
            `Percent increase: ${numberWithCommas(Math.round(value * 100))}%`,
            `Absolute increase: ${numberWithCommas(absoluteIncreaseValue)} ${label}`]
    } else {
        onHoverInfo = [`${numberWithCommas(value)} ${label}`]
    }
    if (disclaimer) return [disclaimer, ...onHoverInfo]
    else return onHoverInfo
}

/**
 * Given a list of parameters, return human readable value that will be displayed on top of the graph's bar.
 * @param geoId: the geoId of the region
 * @param regionName: the name of the region
 * @param date: the date of the observation
 * @param value: the value at that specific date for that specific geoId
 * @param population: the total population of that region
 * @param absoluteIncreaseValue: the absolute difference between day 2 and day 1
 * @param label: Are we talking about cases? or deaths?
 * @param contentType: What is the graph showing? Per-Capita? Increase? Absolute?
 */
const getTextOnTopOfBar = (geoId: string, regionName: string, date: string, value: number, population: number,
                            absoluteIncreaseValue: number, label: string, contentType: string) => {
    const populationWithCommas = numberWithCommas(population)
    let textOnTopOfBar: string;

    if (contentType === 'perCapita' || contentType === 'absolutePerCapita')
        textOnTopOfBar = `${numberWithCommas(absoluteIncreaseValue)} / ${populationWithCommas}`
    else if (contentType === 'increase')
        textOnTopOfBar = `${numberWithCommas(absoluteIncreaseValue)} (${Math.round(value * 100)}%)`
    else {
        textOnTopOfBar = `${numberWithCommas(value)}`
    }

    return textOnTopOfBar
}


/**
 * Generates information for the graph to display. For example, the Bar Graph must know things such as 'name',
 * 'onHoverInfo', and the 'text' to display on top of the bar.
 * @param values: date->geoId->value
 * @param geoIdToPopulation: geoId->Population
 * @param geoIdToName: geoId->name
 * @param absoluteIncrease: absolute increase from one day to the other (optional)
 * @param label: Are we talking about cases or deaths?
 * @param contentType: What is the graph showing? Per-Capita? Increase? Absolute?
 */
export default function generateGraphMetadata(values: DateToGeoIdToValue, geoIdToPopulation: {geoId: number},
                                              geoIdToName: {geoId: string}, absoluteIncrease: DateToGeoIdToValue,
                                              label: string, contentType: string): {date: {geoId: Metadata}} | {} {
    let output: {date: {geoId: Metadata}} | {} = {}

    // For every date and geoId in the dataset
    for (let date in values){
        for (let geoId in values[date]) {
            const population: number = geoIdToPopulation[geoId] || 0
            const regionName: string = geoIdToName[geoId]?.[0] || ""
            const value: number = values[date][geoId] || 0
            const absoluteIncreaseValue: number = absoluteIncrease[date]?.[geoId] || 0

            // Generate the text that is displayed when the user hovers on a graph.
            const onHoverInfo = getOnHoverInfoText(geoId, regionName, date, value, population,
                absoluteIncreaseValue, label, contentType)

            const textOnTopOfBar = getTextOnTopOfBar(geoId, regionName, date, value, population,
                absoluteIncreaseValue, label, contentType)

            // If the date is not in the output, create it.
            if (!(date in output)) output[date] = {}

            output[date][geoId] = {
                name: regionName,
                onHoverInfo: onHoverInfo,
                textOnTopOfBar: textOnTopOfBar
            }
        }
    }
    return output
}