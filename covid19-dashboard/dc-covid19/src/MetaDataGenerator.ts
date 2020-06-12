import {numberWithCommas} from "./Utils";
type Metadata = {
    name: string,
    onHoverInfo: string[]
    textOnTopOfBar: string,
    population: number,
}

type DateToGeoIdToValue = {string: {string: number}} | {}

/**
 * TODO: convert this to a JSON file that can be easily edited.
 * Given a list of parameters, return human readable strings explaining the data.
 * @param geoId: the geoId of the region
 * @param regionName: the name of the region
 * @param date: the date of the observation
 * @param value: the value at that specific date for that specific geoId
 * @param population: the total population of that region
 * @param absoluteIncrease: the absolute difference between day 2 and day 1
 * @param label: Are we talking about cases? or deaths?
 * @param contentType: What is the graph showing? Per-Capita? Increase? Absolute?
 */
const getOnHoverInfoText = (geoId: string, regionName: string, date: string, value: number, population: number,
                             absoluteIncrease: number, label: string, contentType: string) => {
    let disclaimer: string = '', onHoverInfo: string[];
    if (geoId === 'geoId/3651000' || geoId === 'geoId/2938000')
        disclaimer = `All counties in ${regionName} are combined and reported as one.`

    if (contentType === 'perCapita') {
        onHoverInfo = [
            `${value} ${label} per 10,000 people`,
            `New ${label}: ${numberWithCommas(absoluteIncrease)}`,
            `Total population: ${numberWithCommas(population[geoId])} people`]
    } else if (contentType === 'increase') {
        onHoverInfo = [
            `Percent increase: ${numberWithCommas(value)}%`,
            `Absolute increase: ${numberWithCommas(absoluteIncrease[date]?.[geoId])} ${label}`]
    } else {
        onHoverInfo = [`${numberWithCommas(value)} ${label}`]
    }
    return [disclaimer, ...onHoverInfo]
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
            const population: number= geoIdToPopulation[geoId] || 0
            const regionName: string = geoIdToName[geoId]?.[0] || ""
            const value: number = values[date][geoId] || 0
            const absoluteIncreaseValue: number = absoluteIncrease[date]?.[geoId] || 0

            // Generate the text that is displayed when the user hovers on a graph.
            const onHoverInfo = getOnHoverInfoText(date, geoId, regionName, population, value,
                absoluteIncreaseValue, label, contentType)

            // If the date is not in the output, create it.
            if (!(date in output)) output[date] = {}

            output[date][geoId] = {
                name: regionName,
                onHoverInfo: onHoverInfo,
                textOnTopOfBar: ''
            }
        }
    }
    return output
}