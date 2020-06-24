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

import React from 'react'
import Configuration from './Configuration.json'
import {getRealISODatesFromArrayOfDeltaDays} from "./Utils"
import Content from './Content'

type State = {
    allData: {}[], // [cases, deaths, population, names]
    selectedRegion: string, // current region selected
    selectedShowTopN: number, // default number of top counties/states to show
    datePicked: string, // current date selected, latest is always default
    availableRegions: {}, // region -> geoId
    datesToPick: string[] // available dates to pick from, example: today, 1 week ago, 1 month ago,
}

class App extends React.Component <{}, State> {
    state = {
        allData: [{}, {}, {}, {}],
        selectedRegion: "State",
        selectedShowTopN: 10,
        datePicked: "2020-01-01",
        availableRegions: Configuration.REGIONS,
        datesToPick: ["2020-01-01"]
    }

    componentDidMount() {
        const requests = this.fetchData()

        Promise.all(requests).then(responses => {
            console.log(responses)
            responses.forEach((response, index) => {
                response.json().then( json => {
                    // Keep the data stored in the same position, that is: [cases, deaths, population, names]
                    // Make a deep copy of the data stored in this.state.data, and then store the json at the index
                    const currentData = this.state.allData.map(val => val)
                    currentData[index] = json
                    this.setState({allData: currentData})

                    // Index 0 contains the 'total-cases' object, which has the dates as keys.
                    if (index === 0) {
                        // Get an array of all the dates in the data.
                        const allDates = Object.keys(json)
                        const latestDate = allDates[allDates.length - 1]
                        // Get the deltaDates from the Configuration file.
                        const datesToPick = getRealISODatesFromArrayOfDeltaDays(latestDate, Configuration.DATES)
                        this.setState({datesToPick: datesToPick})
                        // The default date is always the latest date available in the dataset,
                        // which happens to be the last date in the array
                        const mostRecentDate = datesToPick[datesToPick.length - 1]
                        this.setState({datePicked: mostRecentDate})
                    // Index 3 contains the 'geoId -> belongsToRegion' object
                    // We can get all the available States
                    } else if (index === 3){
                        let regions: {} = {}
                        Object.keys(json).forEach(geoId => {
                            // Check to see that the region belongsToRegion country/USA
                            if (json[geoId][1] === 'country/USA') regions[geoId] = json[geoId][0]
                        })
                        this.setState({availableRegions: {...this.state.availableRegions, ...regions}})
                    }
                })
            })
        })
    }


    /**
     * In charge of changing the state when the region, date or showTopN are updated.
     * @param key
     * @param value
     */
    handleSelectUpdate = (key: string, value: any) =>{
        switch(key) {
            case 'region':
                this.setState({selectedRegion: value})
                break
            case 'date':
                this.setState({datePicked: value})
                break
            case 'showTopN':
                this.setState({selectedShowTopN: value})
                break
        }
    }

    /**
     * Request the data from the server, and store the Promises in that order.
     * The order is important [cases, deaths, population, places].
     */
    fetchData = () => {
        const url: string = 'http://localhost/api/'
        const apis = [
            url + 'total-cases',
            url + 'total-deaths',
            url + 'population',
            url + 'places']
        // Map every url to the promise of the fetch
        return apis.map(api => fetch(api))
    }
    
    render = () => {
        return (
            <div className={"container"}>
                <h1 className={"main-title"}>
                    {Configuration.TITLE + ' '}
                    <span style={{color: "#990001"}}>{Configuration.SUBTITLE}</span>
                </h1>
                <Content allData={this.state.allData}
                         content={Configuration.content}
                         selectedRegion={this.state.selectedRegion}
                         availableRegions={this.state.availableRegions}
                         datePicked={this.state.datePicked}
                         datesToPick={this.state.datesToPick}
                         region={this.state.selectedRegion}
                         handleSelectUpdate={this.handleSelectUpdate}
                         selectedShowTopN={this.state.selectedShowTopN}/>
            </div>
        )
    }
}

export default App
